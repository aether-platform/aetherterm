"""
Terminal-related Socket.IO event handlers.

薄いアダプター層として、Socket.IOイベントを受け取り、
ユースケースに処理を委譲します。
"""

import asyncio
import logging
from uuid import uuid4

import jinja2
from dependency_injector.wiring import Provide, inject

from aetherterm.agentserver import utils
from aetherterm.agentserver.containers import ApplicationContainer
from aetherterm.agentserver.terminals.asyncio_terminal import AsyncioTerminal
from aetherterm.agentserver.utils import User

from .helpers import get_sio, get_user_info_from_environ

log = logging.getLogger("aetherterm.socket_handlers")


@inject
async def connect(
    sid,
    environ,
    config_motd: str = Provide[ApplicationContainer.config.motd],
):
    """Handle client connection."""
    sio = get_sio()
    log.info(f"Client connected: {sid}")
    await sio.emit("connected", {"data": "Connected to Butterfly"}, room=sid)

    try:
        with open(config_motd, "r") as f:
            motd_content = f.read()

        template = jinja2.Template(motd_content)
        rendered_motd = template.render()

        await sio.emit(
            "terminal_output", {"session": "motd", "data": rendered_motd}, room=sid
        )
    except FileNotFoundError:
        log.warning(f"MOTD file not found: {config_motd}")
    except Exception as e:
        log.error(f"Error reading MOTD file: {e}")


async def disconnect(sid, environ=None):
    """Handle client disconnection."""
    sio = get_sio()
    log.info(f"Client disconnected: {sid}")

    for session_id, terminal in list(AsyncioTerminal.sessions.items()):
        if hasattr(terminal, "client_sids") and sid in terminal.client_sids:
            terminal.client_sids.discard(sid)
            log.info(f"Removed client {sid} from terminal session {session_id}")
            if not terminal.client_sids:
                log.info(f"No clients remaining for session {session_id}, closing terminal")
                await terminal.close()


@inject
async def create_terminal(
    sid,
    data,
    config_login: bool = Provide[ApplicationContainer.config.login],
    config_pam_profile: str = Provide[ApplicationContainer.config.pam_profile],
    config_uri_root_path: str = Provide[ApplicationContainer.config.uri_root_path],
):
    """Handle the creation of a new terminal session."""
    sio = get_sio()
    try:
        session_id = data.get("session", str(uuid4()))
        user_name = data.get("user", "")
        path = data.get("path", "")

        is_specific_session_request = "session" in data and data["session"] != ""

        log.info(f"Creating terminal session {session_id} for client {sid}")
        log.debug(f"Terminal data: user={user_name}, path={path}")

        # Reuse existing active session
        if session_id in AsyncioTerminal.sessions:
            existing_terminal = AsyncioTerminal.sessions[session_id]
            if not existing_terminal.closed:
                log.info(f"Reusing existing terminal session {session_id}")
                existing_terminal.client_sids.add(sid)
                if existing_terminal.history:
                    await sio.emit(
                        "terminal_output",
                        {"session": session_id, "data": existing_terminal.history},
                        room=sid,
                    )
                await sio.emit(
                    "terminal_ready", {"session": session_id, "status": "ready"}, room=sid
                )
                return
            else:
                log.info(f"Attempted to connect to closed session {session_id}")
                environ = getattr(sio, "environ", {}) if sio else {}
                current_user_info = get_user_info_from_environ(environ)
                is_owner = _check_session_ownership(session_id, current_user_info)

                await sio.emit(
                    "terminal_closed",
                    {
                        "session": session_id,
                        "reason": "session_already_closed",
                        "is_owner": is_owner,
                    },
                    room=sid,
                )
                return

        # Check previously closed sessions
        if is_specific_session_request and session_id in AsyncioTerminal.closed_sessions:
            log.info(f"Attempted to connect to previously closed session {session_id}")
            environ = getattr(sio, "environ", {}) if sio else {}
            current_user_info = get_user_info_from_environ(environ)
            is_owner = _check_session_ownership(session_id, current_user_info)

            await sio.emit(
                "terminal_closed",
                {"session": session_id, "reason": "session_already_closed", "is_owner": is_owner},
                room=sid,
            )
            return

        # Create connection info
        environ = getattr(sio, "environ", {}) if sio else {}
        socket_remote_addr = None
        if hasattr(sio, "manager") and hasattr(sio.manager, "get_session"):
            try:
                session = sio.manager.get_session(sid)
                if session and "transport" in session:
                    transport = session["transport"]
                    if hasattr(transport, "socket") and hasattr(transport.socket, "getpeername"):
                        try:
                            peer = transport.socket.getpeername()
                            socket_remote_addr = peer[0]
                            environ["REMOTE_PORT"] = str(peer[1])
                        except Exception:
                            pass
            except Exception:
                pass

        current_user_info = get_user_info_from_environ(environ)
        socket = utils.ConnectionInfo(environ, socket_remote_addr)

        # Determine user
        terminal_user = None
        if user_name:
            try:
                terminal_user = User(name=user_name)
                log.debug(f"Using user: {terminal_user}")
            except LookupError:
                log.warning(f"Invalid user: {user_name}, falling back to default user.")
                terminal_user = User()

        # Create terminal instance
        log.debug("Creating AsyncioTerminal instance")
        terminal_instance = AsyncioTerminal(
            user=terminal_user,
            path=path,
            session=session_id,
            socket=socket,
            uri=f"http://{socket.local_addr}:{socket.local_port}{config_uri_root_path.rstrip('/') if config_uri_root_path else ''}/?session={session_id}",
            render_string=None,
            broadcast=lambda s, m: broadcast_to_session(s, m),
            login=config_login,
            pam_profile=config_pam_profile,
        )

        terminal_instance.client_sids.add(sid)

        log.debug("Starting PTY")
        await terminal_instance.start_pty()
        log.info(f"PTY started successfully for session {session_id}")

        await sio.emit(
            "terminal_ready", {"session": session_id, "status": "ready"}, room=sid
        )
        log.debug(f"Sent terminal_ready event to client {sid}")

    except Exception as e:
        log.error(f"Error creating terminal: {e}", exc_info=True)
        await sio.emit("terminal_error", {"error": str(e)}, room=sid)


async def terminal_input(sid, data):
    """Handle input from client to terminal."""
    try:
        session_id = data.get("session")
        input_data = data.get("data", "")

        if session_id in AsyncioTerminal.sessions:
            terminal = AsyncioTerminal.sessions[session_id]
            await terminal.write(input_data)
        else:
            log.warning(f"Terminal session {session_id} not found")

    except Exception as e:
        log.error(f"Error handling terminal input: {e}")


async def terminal_resize(sid, data):
    """Handle terminal resize from client."""
    try:
        session_id = data.get("session")
        cols = data.get("cols", 80)
        rows = data.get("rows", 24)

        if session_id in AsyncioTerminal.sessions:
            terminal = AsyncioTerminal.sessions[session_id]
            await terminal.resize(cols, rows)
        else:
            log.warning(f"Terminal session {session_id} not found")

    except Exception as e:
        log.error(f"Error handling terminal resize: {e}")


@inject
def broadcast_to_session(
    session_id,
    message,
    terminal_use_cases=Provide[ApplicationContainer.terminal_use_cases],
):
    """Broadcast message to all clients connected to a session.

    TerminalUseCases に処理を委譲し、脅威検出・ブロック・ブロードキャストを実行。
    """
    asyncio.create_task(
        terminal_use_cases.broadcast_terminal_output(session_id, message)
    )


def _check_session_ownership(session_id, current_user_info):
    """Check if the current user is the owner of the session."""
    from aetherterm.agentserver.domain.entities import SessionOwner, UserInfo, check_session_ownership

    if session_id not in AsyncioTerminal.session_owners:
        return False

    owner_info = AsyncioTerminal.session_owners[session_id]
    owner = SessionOwner(
        remote_addr=owner_info.get("remote_addr"),
        remote_user=owner_info.get("remote_user"),
        user_name=owner_info.get("user_name"),
        created_at=owner_info.get("created_at", 0),
    )
    user_info = UserInfo(
        remote_addr=current_user_info.get("remote_addr"),
        remote_user=current_user_info.get("remote_user"),
    )
    return check_session_ownership(owner, user_info)

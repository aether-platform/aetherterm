"""
Terminal-related Socket.IO event handlers.

薄いアダプター層として、Socket.IOイベントを受け取り、
ユースケースとリポジトリに処理を委譲します。
AsyncioTerminal への直接アクセスはターミナル生成時のみ。
"""

import asyncio
import logging
from uuid import uuid4

import jinja2
from dependency_injector.wiring import Provide, inject

from aetherterm.agentserver import utils
from aetherterm.agentserver.containers import ApplicationContainer
from aetherterm.agentserver.domain.entities import UserInfo, check_session_ownership
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


@inject
async def disconnect(
    sid,
    environ=None,
    terminal_repo=Provide[ApplicationContainer.terminal_repo],
):
    """Handle client disconnection."""
    log.info(f"Client disconnected: {sid}")

    session_ids = terminal_repo.get_all_sessions_for_client(sid)
    for session_id in session_ids:
        remaining = terminal_repo.remove_client_from_session(session_id, sid)
        log.info(f"Removed client {sid} from terminal session {session_id}")
        if remaining == 0:
            log.info(f"No clients remaining for session {session_id}, closing terminal")
            await terminal_repo.close_session(session_id)


@inject
async def create_terminal(
    sid,
    data,
    config_login: bool = Provide[ApplicationContainer.config.login],
    config_pam_profile: str = Provide[ApplicationContainer.config.pam_profile],
    config_uri_root_path: str = Provide[ApplicationContainer.config.uri_root_path],
    terminal_repo=Provide[ApplicationContainer.terminal_repo],
    broadcaster=Provide[ApplicationContainer.broadcaster],
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
        if terminal_repo.session_exists(session_id):
            session_info = terminal_repo.get_session_info(session_id)
            if session_info and not session_info.is_closed:
                log.info(f"Reusing existing terminal session {session_id}")
                terminal_repo.add_client_to_session(session_id, sid)
                if session_info.history:
                    await broadcaster.emit_to_client(
                        "terminal_output",
                        {"session": session_id, "data": session_info.history},
                        sid,
                    )
                await broadcaster.emit_to_client(
                    "terminal_ready", {"session": session_id, "status": "ready"}, sid
                )
                return
            else:
                log.info(f"Attempted to connect to closed session {session_id}")
                environ = getattr(sio, "environ", {}) if sio else {}
                current_user_info = get_user_info_from_environ(environ)
                is_owner = _check_ownership_via_repo(terminal_repo, session_id, current_user_info)

                await broadcaster.emit_to_client(
                    "terminal_closed",
                    {
                        "session": session_id,
                        "reason": "session_already_closed",
                        "is_owner": is_owner,
                    },
                    sid,
                )
                return

        # Check previously closed sessions
        if is_specific_session_request and terminal_repo.is_session_closed(session_id):
            log.info(f"Attempted to connect to previously closed session {session_id}")
            environ = getattr(sio, "environ", {}) if sio else {}
            current_user_info = get_user_info_from_environ(environ)
            is_owner = _check_ownership_via_repo(terminal_repo, session_id, current_user_info)

            await broadcaster.emit_to_client(
                "terminal_closed",
                {"session": session_id, "reason": "session_already_closed", "is_owner": is_owner},
                sid,
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

        # Create terminal instance (AsyncioTerminal auto-registers in sessions dict)
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

        await broadcaster.emit_to_client(
            "terminal_ready", {"session": session_id, "status": "ready"}, sid
        )
        log.debug(f"Sent terminal_ready event to client {sid}")

    except Exception as e:
        log.error(f"Error creating terminal: {e}", exc_info=True)
        await sio.emit("terminal_error", {"error": str(e)}, room=sid)


@inject
async def terminal_input(
    sid,
    data,
    terminal_repo=Provide[ApplicationContainer.terminal_repo],
):
    """Handle input from client to terminal."""
    try:
        session_id = data.get("session")
        input_data = data.get("data", "")

        if not await terminal_repo.write_to_session(session_id, input_data):
            log.warning(f"Terminal session {session_id} not found")

    except Exception as e:
        log.error(f"Error handling terminal input: {e}")


@inject
async def terminal_resize(
    sid,
    data,
    terminal_repo=Provide[ApplicationContainer.terminal_repo],
):
    """Handle terminal resize from client."""
    try:
        session_id = data.get("session")
        cols = data.get("cols", 80)
        rows = data.get("rows", 24)

        if not await terminal_repo.resize_session(session_id, cols, rows):
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


def _check_ownership_via_repo(terminal_repo, session_id, current_user_info):
    """リポジトリ経由でセッション所有権を確認"""
    owner = terminal_repo.get_session_owner(session_id)
    if owner is None:
        return False

    user_info = UserInfo(
        remote_addr=current_user_info.get("remote_addr"),
        remote_user=current_user_info.get("remote_user"),
    )
    return check_session_ownership(owner, user_info)

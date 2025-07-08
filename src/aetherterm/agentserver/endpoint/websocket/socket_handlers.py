import asyncio
import logging
from datetime import datetime
from uuid import uuid4

from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal
from aetherterm.agentserver.infrastructure.config import utils
from aetherterm.agentserver.infrastructure.config.utils import User
from aetherterm.agentserver.infrastructure import get_ai_service
from aetherterm.agentserver.infrastructure.logging.log_analyzer import (
    get_log_analyzer,
    SeverityLevel,
)

log = logging.getLogger("aetherterm.socket_handlers")

# Global storage for socket.io server instance
sio_instance = None
log_processing_manager = None


# Error handling decorator to reduce duplicate try-catch blocks
def socket_error_handler(error_event: str = "error"):
    """Decorator to handle socket operation errors consistently."""

    def decorator(func):
        async def wrapper(sid, data, *args, **kwargs):
            try:
                return await func(sid, data, *args, **kwargs)
            except Exception as e:
                log.error(f"Error in {func.__name__}: {e}", exc_info=True)
                await sio_instance.emit(error_event, {"error": str(e)}, room=sid)

        return wrapper

    return decorator


def set_sio_instance(sio):
    """Set the global socket.io server instance."""
    global sio_instance
    sio_instance = sio
    log.info("Socket.IO instance configured")


def get_user_info_from_environ(environ):
    """Extract user information from environment/headers."""
    user_info = {
        "remote_addr": environ.get("REMOTE_ADDR"),
        "remote_user": environ.get("HTTP_X_REMOTE_USER"),
        "user_agent": environ.get("HTTP_USER_AGENT"),
        "roles": [],
    }

    # Simple role extraction - check common headers
    for header in ["HTTP_X_AUTH_ROLES", "HTTP_X_USER_ROLES", "HTTP_X_ROLES"]:
        header_value = environ.get(header)
        if header_value:
            user_info["roles"] = [r.strip() for r in header_value.split(",")]
            break

    return user_info


def check_session_ownership(session_id, current_user_info):
    """Check if the current user is the owner of the session."""
    if session_id not in AsyncioTerminal.session_owners:
        return False

    owner_info = AsyncioTerminal.session_owners[session_id]

    # Check X-REMOTE-USER header (most reliable for authenticated users)
    if (
        current_user_info.get("remote_user")
        and owner_info.get("remote_user")
        and current_user_info["remote_user"] == owner_info["remote_user"]
    ):
        return True

    # Fallback to IP address comparison (less reliable but works for unsecure mode)
    if (
        current_user_info.get("remote_addr")
        and owner_info.get("remote_addr")
        and current_user_info["remote_addr"] == owner_info["remote_addr"]
    ):
        return True

    return False


async def connect(
    sid,
    environ,
    auth=None,
):
    """Handle client connection."""
    log.info(f"Client connected: {sid}")

    # Extract user info from environment to determine role
    user_info = get_user_info_from_environ(environ)
    user_roles = user_info.get("roles", [])
    role = "Viewer" if "Viewer" in user_roles else "User"

    # Add user to global workspace
    from aetherterm.agentserver.domain.services.global_workspace_service import (
        get_global_workspace_service,
    )

    global_service = get_global_workspace_service()
    global_service.add_user(sid, role)
    log.info(f"Added user {sid} to global workspace with role: {role}")

    # For global workspace, no token handling needed - simplified architecture

    await sio_instance.emit("connected", {"data": "Connected to Butterfly"}, room=sid)

    try:
        # Simple welcome message instead of file-based MOTD
        motd_content = "Welcome to AetherTerm - AI Terminal Platform\r\n"

        await sio_instance.emit(
            "terminal_output", {"session": "motd", "data": motd_content}, room=sid
        )
    except Exception as e:
        log.error(f"Error sending MOTD: {e}")


async def disconnect(sid, environ=None):
    """Handle client disconnection."""
    log.info(f"Client disconnected: {sid}")

    # Remove user from global workspace
    from aetherterm.agentserver.domain.services.global_workspace_service import (
        get_global_workspace_service,
    )

    global_service = get_global_workspace_service()
    global_service.remove_user(sid)

    # For global workspace, no token handling needed - simplified architecture

    # Remove client from any terminal sessions and schedule delayed closure if no clients remain
    for session_id, terminal in list(AsyncioTerminal.sessions.items()):
        if hasattr(terminal, "client_sids") and sid in terminal.client_sids:
            terminal.client_sids.discard(sid)
            log.info(f"Removed client {sid} from terminal session {session_id}")
            # If no clients remain, schedule delayed terminal closure
            if not terminal.client_sids:
                log.info(
                    f"No clients remaining for session {session_id}, scheduling delayed closure"
                )
                # Add a grace period of 30 seconds for reconnection
                await _schedule_terminal_closure(session_id, terminal, grace_period=30)


async def _schedule_terminal_closure(session_id: str, terminal, grace_period: int = 30):
    """Schedule terminal closure after a grace period, cancelling if clients reconnect."""
    import asyncio

    # Mark terminal as pending closure
    if not hasattr(terminal, "_closure_task") or terminal._closure_task is None:
        terminal._closure_task = asyncio.create_task(
            _delayed_terminal_closure(session_id, terminal, grace_period)
        )


async def _delayed_terminal_closure(session_id: str, terminal, grace_period: int):
    """Execute delayed terminal closure, checking for client reconnection."""
    import asyncio

    try:
        log.info(
            f"Grace period started for session {session_id}, waiting {grace_period} seconds for reconnection"
        )
        await asyncio.sleep(grace_period)

        # Check if clients have reconnected during grace period
        if hasattr(terminal, "client_sids") and terminal.client_sids:
            log.info(f"Clients reconnected to session {session_id}, cancelling closure")
            return

        # Check if terminal is still active and not already closed
        if session_id in AsyncioTerminal.sessions and not terminal.closed:
            log.info(f"Grace period expired for session {session_id}, closing terminal")
            await terminal.close()
        else:
            log.info(f"Session {session_id} already closed or removed")

    except asyncio.CancelledError:
        log.info(f"Terminal closure cancelled for session {session_id} - client reconnected")
    except Exception as e:
        log.error(f"Error during delayed terminal closure for session {session_id}: {e}")
    finally:
        # Clear the closure task reference
        if hasattr(terminal, "_closure_task"):
            terminal._closure_task = None


# @inject  # Temporarily disabled for testing
async def create_terminal(
    sid,
    data,
    config_login: bool = False,  # Provide[ApplicationContainer.config.login],
    config_pam_profile: str = "",  # Provide[ApplicationContainer.config.pam_profile],
    config_uri_root_path: str = "",  # Provide[ApplicationContainer.config.uri_root_path],
):
    """Handle the creation of a new terminal session with optional agent configuration."""
    try:
        # Check if user has permission to create terminals
        from aetherterm.agentserver.domain.services.global_workspace_service import (
            get_global_workspace_service,
        )

        global_service = get_global_workspace_service()

        if not global_service.can_user_modify(sid):
            log.warning(f"User {sid} (Viewer) attempted to create terminal")
            await sio_instance.emit(
                "terminal_error", {"error": "Viewers cannot create terminals"}, room=sid
            )
            return
        session_id = data.get("session", str(uuid4()))
        user_name = data.get("user", "")
        path = data.get("path", "")

        # P0 緊急対応: エージェント起動設定
        launch_mode = data.get("launch_mode", "default")  # default, agent
        agent_config = data.get("agent_config", {})
        agent_type = agent_config.get(
            "agent_type"
        )  # developer, reviewer, tester, architect, researcher
        requester_agent_id = data.get("requester_agent_id")  # MainAgentからの要請の場合

        # Get pane_id and tab_id from data
        pane_id = data.get("paneId")
        tab_id = data.get("tabId")

        # Check if this is a request for a specific session (not a new random one)
        is_specific_session_request = "session" in data and data["session"] != ""

        # For global workspace, we use the provided session ID directly
        # No need to search for existing sessions across workspace tokens

        log.info(f"Creating terminal session {session_id} for client {sid}")
        log.debug(f"Terminal data: user={user_name}, path={path}")

        # Check if session already exists and is still active
        if session_id in AsyncioTerminal.sessions:
            existing_terminal = AsyncioTerminal.sessions[session_id]
            if not existing_terminal.closed:
                log.info(f"Reusing existing terminal session {session_id}")

                # Cancel any pending closure task since client is reconnecting
                if hasattr(existing_terminal, "_closure_task") and existing_terminal._closure_task:
                    existing_terminal._closure_task.cancel()
                    existing_terminal._closure_task = None
                    log.info(f"Cancelled pending closure for session {session_id}")

                # Add this client to the existing terminal's client set
                existing_terminal.client_sids.add(sid)
                # Send terminal history to new client
                await send_terminal_history(sid, session_id, existing_terminal)
                # Notify client that terminal is ready
                await sio_instance.emit(
                    "terminal_ready", {"session": session_id, "status": "ready"}, room=sid
                )
                return
            # Session exists but is closed - check ownership and notify client
            log.info(f"Attempted to connect to closed session {session_id}")
            # Get environ for user info checking
            environ = getattr(sio_instance, "environ", {}) if sio_instance else {}
            current_user_info = get_user_info_from_environ(environ)
            is_owner = check_session_ownership(session_id, current_user_info)

            await sio_instance.emit(
                "terminal_closed",
                {
                    "session": session_id,
                    "reason": "session_already_closed",
                    "is_owner": is_owner,
                },
                room=sid,
            )
            return

        # Check if this is a request for a specific session that was previously closed
        if is_specific_session_request and session_id in AsyncioTerminal.closed_sessions:
            log.info(f"Attempted to connect to previously closed session {session_id}")
            # Get environ for user info checking
            environ = getattr(sio_instance, "environ", {}) if sio_instance else {}
            current_user_info = get_user_info_from_environ(environ)
            is_owner = check_session_ownership(session_id, current_user_info)

            await sio_instance.emit(
                "terminal_closed",
                {"session": session_id, "reason": "session_already_closed", "is_owner": is_owner},
                room=sid,
            )
            return

        # Create connection info for Socket.IO
        # Get environ from Socket.IO if available, otherwise use defaults
        environ = getattr(sio_instance, "environ", {}) if sio_instance else {}

        # Try to get more accurate socket information from the session
        # For Socket.IO, we need to extract the real client information
        socket_remote_addr = None
        if hasattr(sio_instance, "manager") and hasattr(sio_instance.manager, "get_session"):
            try:
                session = sio_instance.manager.get_session(sid)
                if session and "transport" in session:
                    transport = session["transport"]
                    if hasattr(transport, "socket") and hasattr(transport.socket, "getpeername"):
                        try:
                            peer = transport.socket.getpeername()
                            socket_remote_addr = peer[0]
                            # Update environ with real remote port
                            environ["REMOTE_PORT"] = str(peer[1])
                        except:
                            pass
            except:
                pass

        # Get current user info for ownership checking
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
                terminal_user = User()  # Fallback to current user

        # Create terminal instance with agent configuration
        log.debug(f"Creating AsyncioTerminal instance with launch_mode: {launch_mode}")

        # P0 緊急対応: エージェント起動コマンドの準備
        startup_command = None
        if launch_mode == "agent" and agent_type:
            # 特定エージェント起動コマンド
            startup_command = _build_agent_command(agent_type, agent_config)

        terminal_instance = AsyncioTerminal(
            user=terminal_user,
            path=path,
            session=session_id,
            socket=socket,
            uri=f"http://{socket.local_addr}:{socket.local_port}{config_uri_root_path.rstrip('/') if config_uri_root_path else ''}/?session={session_id}",  # Full sharing URL with root path
            render_string=None,  # Not used in asyncio_terminal directly for MOTD rendering
            broadcast=lambda s, m: broadcast_to_session(s, m),
            login=config_login,
            pam_profile=config_pam_profile,
        )

        # Store agent configuration for tracking
        if launch_mode == "agent":
            terminal_instance.agent_config = {
                "launch_mode": launch_mode,
                "agent_type": agent_type,
                "agent_config": agent_config,
                "requester_agent_id": requester_agent_id,
                "startup_command": startup_command,
                "agent_hierarchy": "sub" if requester_agent_id else "main",
                "parent_agent_id": requester_agent_id,
            }

        # Associate terminal with client using the new client set
        terminal_instance.client_sids.add(sid)

        # Store metadata for session restoration in global workspace
        # Find tab and pane indices from the create_terminal call context
        # This is set during resume_workspace when creating new terminals
        if (
            hasattr(AsyncioTerminal, "_temp_creation_context")
            and AsyncioTerminal._temp_creation_context
        ):
            terminal_instance.tab_index = AsyncioTerminal._temp_creation_context.get(
                "tab_index", 0
            )
            terminal_instance.pane_index = AsyncioTerminal._temp_creation_context.get(
                "pane_index", 0
            )
        else:
            # Default to 0 if not in resume context
            terminal_instance.tab_index = 0
            terminal_instance.pane_index = 0
        log.info(
            f"Terminal {session_id} created in global workspace tab[{terminal_instance.tab_index}] pane[{terminal_instance.pane_index}]"
        )

        # Start the PTY
        log.debug("Starting PTY")
        await terminal_instance.start_pty()
        log.info(f"PTY started successfully for session {session_id}")

        # P0 緊急対応: エージェント自動起動
        if startup_command and launch_mode == "agent":
            try:
                log.info(f"Auto-starting {launch_mode} with command: {startup_command}")
                await asyncio.sleep(1)  # PTY初期化待ち
                await terminal_instance.write(startup_command + "\n")

                # MainAgentに通知（ブロードキャスト形式）
                if requester_agent_id:
                    await sio_instance.emit(
                        "agent_message",
                        {
                            "message_type": "agent_start_response",
                            "requester_agent_id": requester_agent_id,
                            "session_id": session_id,
                            "agent_type": agent_type,
                            "agent_id": agent_config.get("agent_id"),
                            "status": "started",
                            "launch_mode": launch_mode,
                            "hierarchy": "sub",
                            "parent_agent_id": requester_agent_id,
                            "working_directory": agent_config.get("working_directory"),
                            "timestamp": datetime.utcnow().isoformat(),
                        },
                    )

                # 新しく起動したエージェントに初期情報を送信
                await asyncio.sleep(2)  # エージェントの初期化待ち
                await sio_instance.emit(
                    "agent_message",
                    {
                        "message_type": "agent_initialization",
                        "to_agent_id": agent_config.get("agent_id"),
                        "agent_info": {
                            "agent_id": agent_config.get("agent_id"),
                            "agent_type": agent_type,
                            "role": "sub_agent",
                            "hierarchy": "sub" if requester_agent_id else "main",
                            "parent_agent_id": requester_agent_id,
                            "working_directory": agent_config.get("working_directory"),
                            "session_id": session_id,
                            "launch_mode": launch_mode,
                            "server_info": {
                                "websocket_url": "ws://localhost:57575",
                                "rest_api_base": "http://localhost:57575/api/v1",
                            },
                            "capabilities": _get_agent_capabilities(agent_type),
                            "instructions": _get_agent_instructions(agent_type, requester_agent_id),
                        },
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )
            except Exception as e:
                log.error(f"Failed to auto-start agent: {e}")

        # Initialize log capture for this terminal
        if log_processing_manager:
            try:
                await log_processing_manager.initialize_terminal_capture(session_id)
                log.debug(f"Log capture initialized for session {session_id}")
            except Exception as e:
                log.error(f"Failed to initialize log capture for session {session_id}: {e}")

        # Notify client that terminal is ready
        response_data = {"session": session_id, "status": "ready"}
        if launch_mode == "agent":
            response_data.update(
                {"launch_mode": launch_mode, "agent_type": agent_type, "agent_config": agent_config}
            )

        await sio_instance.emit("terminal_ready", response_data, room=sid)
        log.debug(f"Sent terminal_ready event to client {sid}")

    except Exception as e:
        log.error(f"Error creating terminal: {e}", exc_info=True)
        await sio_instance.emit("terminal_error", {"error": str(e)}, room=sid)


async def resume_workspace(sid, data):
    """Handle resuming an entire workspace with multiple tabs, panes and sessions."""
    try:
        workspace_id = data.get("workspaceId")
        tabs = data.get("tabs", [])  # Each tab can contain multiple panes

        log.info(
            f"Resume workspace request for workspace {workspace_id} with {len(tabs)} tabs from client {sid}"
        )

        if not workspace_id:
            log.warning("Resume workspace request without workspaceId")
            await sio_instance.emit(
                "workspace_error", {"error": "workspaceId required for workspace resume"}, room=sid
            )
            return

        # Process each tab with panes in the workspace
        resumed_tabs = []
        created_tabs = []

        for tab_data in tabs:
            tab_id = tab_data.get("id")
            tab_title = tab_data.get("title", "Tab")
            tab_layout = tab_data.get("layout", "single")
            panes = tab_data.get("panes", [])

            if not tab_id:
                log.warning(f"Tab data missing id, skipping: {tab_data}")
                continue

            log.info(f"Processing tab {tab_id} with {len(panes)} panes")

            # Process each pane in the tab
            resumed_panes = []
            created_panes = []

            for pane_data in panes:
                pane_id = pane_data.get("id")
                session_id = pane_data.get("sessionId")
                pane_type = pane_data.get("type", "terminal")
                sub_type = pane_data.get("subType", "pure")
                pane_title = pane_data.get("title", "Terminal")
                position = pane_data.get("position", {"x": 0, "y": 0, "width": 100, "height": 100})

                if not pane_id:
                    log.warning(f"Pane data missing id, skipping: {pane_data}")
                    continue

                log.info(f"Processing pane {pane_id} with session {session_id}")

                # For global workspace, we use the session ID directly if available
                # Simplified session restoration without workspace token dependencies
                tab_index = tabs.index(tab_data)
                pane_index = panes.index(pane_data)

                # Look for existing session by session ID
                session_found = False

                # Check if session exists by the provided session_id
                if session_id and session_id in AsyncioTerminal.sessions:
                    existing_terminal = AsyncioTerminal.sessions[session_id]
                    if not existing_terminal.closed:
                        log.info(
                            f"Resuming existing active terminal session {session_id} for pane {pane_id}"
                        )

                        # Add this client to the existing terminal's client set
                        existing_terminal.client_sids.add(sid)

                        # Update terminal metadata for future lookups
                        existing_terminal.tab_index = tab_index
                        existing_terminal.pane_index = pane_index

                        # Don't send history here - let the terminal component request it
                        # when it's ready via reconnect_session
                        log.info(
                            f"Terminal {session_id} exists, client should reconnect when ready"
                        )

                        resumed_panes.append(
                            {
                                "paneId": pane_id,
                                "sessionId": session_id,
                                "status": "resumed",
                                "type": pane_type,
                                "subType": sub_type,
                                "title": pane_title,
                                "position": position,
                            }
                        )
                        continue
                    log.info(
                        f"Session {session_id} exists but is closed for pane {pane_id}, will create new"
                    )
                else:
                    log.info(f"Session {session_id} not found for pane {pane_id}, will create new")

                # Session doesn't exist or is closed - create new terminal
                # Generate new session ID if none provided or if session was closed
                new_session_id = session_id or f"terminal_{pane_id}_{uuid4().hex[:8]}"

                log.info(f"Creating new terminal session {new_session_id} for pane {pane_id}")

                # Store creation context in AsyncioTerminal class temporarily
                # so create_terminal can access it
                AsyncioTerminal._temp_creation_context = {
                    "tab_index": tab_index,
                    "pane_index": pane_index,
                }

                # Create new terminal session
                await create_terminal(
                    sid,
                    {
                        "session": new_session_id,
                        "tabId": tab_id,
                        "paneId": pane_id,
                        "subType": sub_type,
                        "type": pane_type,
                        "cols": 80,
                        "rows": 24,
                        "user": "",
                        "path": "",
                    },
                )

                # Clean up temporary context
                AsyncioTerminal._temp_creation_context = None

                created_panes.append(
                    {
                        "paneId": pane_id,
                        "sessionId": new_session_id,
                        "status": "created",
                        "type": pane_type,
                        "subType": sub_type,
                        "title": pane_title,
                        "position": position,
                    }
                )

            # Add tab result with panes
            if resumed_panes:
                resumed_tabs.append(
                    {
                        "tabId": tab_id,
                        "title": tab_title,
                        "layout": tab_layout,
                        "panes": resumed_panes,
                        "status": "resumed",
                    }
                )

            if created_panes:
                created_tabs.append(
                    {
                        "tabId": tab_id,
                        "title": tab_title,
                        "layout": tab_layout,
                        "panes": created_panes,
                        "status": "created",
                    }
                )

        # Send workspace resume response
        await sio_instance.emit(
            "workspace_resumed",
            {
                "workspaceId": workspace_id,
                "status": "success",
                "resumedTabs": resumed_tabs,
                "createdTabs": created_tabs,
                "totalTabs": len(tabs),
                "totalPanes": sum(len(tab.get("panes", [])) for tab in resumed_tabs + created_tabs),
                "message": f"Workspace resumed with {len(resumed_tabs)} existing and {len(created_tabs)} new tab configurations",
            },
            room=sid,
        )

        log.info(
            f"Workspace {workspace_id} resumed successfully: {len(resumed_tabs)} resumed, {len(created_tabs)} created"
        )

    except Exception as e:
        log.error(f"Error resuming workspace: {e}", exc_info=True)
        await sio_instance.emit("workspace_error", {"error": str(e)}, room=sid)


async def resume_terminal(sid, data):
    """Handle resuming an existing terminal session or create new if not found."""
    try:
        session_id = data.get("sessionId")
        tab_id = data.get("tabId")
        sub_type = data.get("subType")
        cols = data.get("cols", 80)
        rows = data.get("rows", 24)

        log.info(f"Resume terminal request for session {session_id} from client {sid}")

        if not session_id:
            log.warning("Resume terminal request without sessionId")
            await sio_instance.emit(
                "terminal_error", {"error": "sessionId required for resume"}, room=sid
            )
            return

        # Check if session exists and is active
        if session_id in AsyncioTerminal.sessions:
            existing_terminal = AsyncioTerminal.sessions[session_id]
            if not existing_terminal.closed:
                log.info(f"Resuming existing active terminal session {session_id}")

                # Add this client to the existing terminal's client set
                existing_terminal.client_sids.add(sid)

                # Send terminal history to client if available
                if existing_terminal.history:
                    await sio_instance.emit(
                        "terminal_output",
                        {"session": session_id, "data": existing_terminal.history},
                        room=sid,
                    )

                # Notify client that terminal is ready (resumed)
                await sio_instance.emit(
                    "terminal_ready",
                    {
                        "session": session_id,
                        "status": "resumed",
                        "tabId": tab_id,
                        "subType": sub_type,
                    },
                    room=sid,
                )
                log.info(f"Terminal session {session_id} successfully resumed for client {sid}")
                return
            log.info(f"Session {session_id} exists but is closed, will create new terminal")
        else:
            log.info(f"Session {session_id} not found, will create new terminal")

        # Session doesn't exist or is closed - create new terminal with the provided session ID
        log.info(f"Creating new terminal session with ID {session_id}")

        # Use create_terminal to create new session with specified session_id
        await create_terminal(
            sid,
            {
                "session": session_id,
                "tabId": tab_id,
                "subType": sub_type,
                "cols": cols,
                "rows": rows,
                "user": "",
                "path": "",
            },
        )

    except Exception as e:
        log.error(f"Error resuming terminal: {e}", exc_info=True)
        await sio_instance.emit("terminal_error", {"error": str(e)}, room=sid)


async def get_session_info(sid, data):
    """Get information about a session for debugging."""
    try:
        session_id = data.get("session")
        if not session_id:
            await sio_instance.emit("session_info", {"error": "No session ID provided"}, room=sid)
            return

        info = {
            "sessionId": session_id,
            "exists": False,
            "active": False,
            "clientCount": 0,
            "history": False,
            "historyLength": 0,
        }

        # Check if session exists in AsyncioTerminal sessions
        if session_id in AsyncioTerminal.sessions:
            terminal = AsyncioTerminal.sessions[session_id]
            info["exists"] = True
            info["active"] = not terminal.closed
            info["clientCount"] = len(terminal.client_sids)
            info["history"] = bool(terminal.history)
            info["historyLength"] = len(terminal.history) if terminal.history else 0

            log.debug(
                f"Session info for {session_id}: exists={info['exists']}, active={info['active']}, clients={info['clientCount']}, history_len={info['historyLength']}"
            )
        else:
            log.info(f"Session {session_id} not found in active sessions")

        await sio_instance.emit("session_info", info, room=sid)

    except Exception as e:
        log.error(f"Error getting session info: {e}", exc_info=True)
        await sio_instance.emit("session_info", {"error": str(e)}, room=sid)


@socket_error_handler("terminal_error")
async def terminal_input(sid, data):
    """Handle input from client to terminal."""
    session_id = data.get("session")
    input_data = data.get("data", "")

    # Check if user has permission to send input using global workspace service
    from aetherterm.agentserver.domain.services.global_workspace_service import (
        get_global_workspace_service,
    )

    global_service = get_global_workspace_service()

    if not global_service.can_user_modify(sid):
        log.warning(f"Input blocked for Viewer role user {sid} in session {session_id}")
        # Send a message back to the client about the restriction
        await sio_instance.emit(
            "terminal_output",
            {
                "session": session_id,
                "data": "\r\n\x1b[33m[Input blocked: Read-only access for Viewer role]\x1b[0m\r\n",
            },
            room=sid,
        )
        return

    if session_id in AsyncioTerminal.sessions:
        terminal = AsyncioTerminal.sessions[session_id]
        await terminal.write(input_data)
    else:
        log.warning(f"Terminal session {session_id} not found")


@socket_error_handler("terminal_error")
async def terminal_resize(sid, data):
    """Handle terminal resize from client."""
    session_id = data.get("session")
    cols = data.get("cols", 80)
    rows = data.get("rows", 24)

    if session_id in AsyncioTerminal.sessions:
        terminal = AsyncioTerminal.sessions[session_id]
        await terminal.resize(cols, rows)
    else:
        log.warning(f"Terminal session {session_id} not found")


def broadcast_to_session(session_id, message):
    """Broadcast message to all clients connected to a session."""
    if sio_instance:
        import asyncio

        # Capture terminal output for log processing
        if log_processing_manager and message:
            try:
                asyncio.create_task(
                    log_processing_manager.capture_terminal_output(session_id, message)
                )
            except Exception as e:
                log.error(f"Failed to capture terminal output: {e}")

        # Get the terminal to find connected clients
        terminal = AsyncioTerminal.sessions.get(session_id)
        if terminal and hasattr(terminal, "client_sids"):
            client_sids = list(terminal.client_sids)
        else:
            client_sids = []

        if message is not None:
            # リアルタイムログ解析を実行 (simplified for now)
            try:
                log_analyzer = get_log_analyzer()
                detection_result = log_analyzer.analyze_output(session_id, message)

                if (
                    detection_result
                    and hasattr(detection_result, "should_block")
                    and detection_result.should_block
                ):
                    log.warning(
                        f"Potentially dangerous output detected in session {session_id}: {detection_result.message}"
                    )
                    # TODO: Implement auto-blocking feature
            except Exception as e:
                log.debug(f"Log analysis failed: {e}")
                # Continue without blocking on log analysis errors

            # Terminal output - broadcast to all clients in this session
            for client_sid in client_sids:
                asyncio.create_task(
                    sio_instance.emit(
                        "terminal_output", {"session": session_id, "data": message}, room=client_sid
                    )
                )
        else:
            # Terminal closed - notify all clients in this session
            log.info(
                f"Broadcasting terminal closed for session {session_id} to {len(client_sids)} clients"
            )
            for client_sid in client_sids:
                asyncio.create_task(
                    sio_instance.emit("terminal_closed", {"session": session_id}, room=client_sid)
                )
    else:
        log.warning("sio_instance is None, cannot broadcast message")


def _build_agent_command(agent_type: str, agent_config: dict) -> str:
    """
    MainAgentの指示に基づいて起動コマンドを構築

    Args:
        agent_type: エージェントタイプ (developer, reviewer, tester, architect, researcher)
        agent_config: エージェント設定

    Returns:
        起動コマンド文字列
    """
    agent_id = agent_config.get("agent_id", f"{agent_type}_agent")
    working_dir = agent_config.get("working_directory", ".")
    requester_agent_id = agent_config.get("requester_agent_id")
    startup_method = agent_config.get("startup_method", "claude_cli")
    custom_startup_command = agent_config.get("custom_startup_command")
    custom_env_vars = agent_config.get("custom_environment_vars", {})

    # 共通の環境変数設定
    base_env_vars = [
        f"AGENT_ID={agent_id}",
        f"AGENT_TYPE={agent_type}",
        "AGENT_ROLE=sub_agent",
        "AETHERTERM_SERVER=ws://localhost:57575",
    ]

    # 要求元エージェントがある場合は追加
    if requester_agent_id:
        base_env_vars.append(f"PARENT_AGENT_ID={requester_agent_id}")
        base_env_vars.append("AGENT_HIERARCHY=sub")
    else:
        base_env_vars.append("AGENT_HIERARCHY=main")

    # MainAgentが指定したカスタム環境変数を追加
    for key, value in custom_env_vars.items():
        base_env_vars.append(f"{key}={value}")

    env_vars_str = " ".join(base_env_vars)

    # MainAgentがカスタム起動コマンドを指定している場合
    if custom_startup_command:
        # プレースホルダーを置換
        command = custom_startup_command.format(
            agent_id=agent_id,
            agent_type=agent_type,
            working_directory=working_dir,
            parent_agent_id=requester_agent_id or "",
        )
        return f"cd {working_dir} && {env_vars_str} {command}"

    # 起動メソッド別のコマンド構築
    if startup_method == "docker":
        # Dockerコンテナでエージェントを起動
        docker_image = agent_config.get("docker_image", f"aether-agent-{agent_type}:latest")
        return f"cd {working_dir} && {env_vars_str} docker run --rm -v $(pwd):/workspace -e AGENT_ID={agent_id} -e AGENT_TYPE={agent_type} {docker_image}"

    if startup_method == "custom_script":
        # カスタムスクリプトで起動
        script_path = agent_config.get("script_path", f"./scripts/start-{agent_type}-agent.sh")
        return f"cd {working_dir} && {env_vars_str} {script_path} {agent_id}"

    # startup_method == "claude_cli" or default
    # エージェントタイプ別のClaude CLIコマンド構築
    if agent_type == "developer":
        return f"cd {working_dir} && {env_vars_str} claude --name {agent_id} --role developer --sub-agent"
    if agent_type == "reviewer":
        return f"cd {working_dir} && {env_vars_str} claude --name {agent_id} --role reviewer --mode review --sub-agent"
    if agent_type == "tester":
        return f"cd {working_dir} && {env_vars_str} claude --name {agent_id} --role tester --mode test --sub-agent"
    if agent_type == "architect":
        return f"cd {working_dir} && {env_vars_str} claude --name {agent_id} --role architect --mode design --sub-agent"
    if agent_type == "researcher":
        return f"cd {working_dir} && {env_vars_str} claude --name {agent_id} --role researcher --mode analyze --sub-agent"
    return f"cd {working_dir} && {env_vars_str} claude --name {agent_id} --sub-agent"


async def agent_start_request(sid, data):
    """
    エージェント起動要請を処理

    メッセージフォーマット:
    {
        "requester_agent_id": "claude_main_001",
        "agent_type": "tester",
        "agent_id": "claude_tester_002",
        "working_directory": "/workspace/project",
        "launch_mode": "agent",
        "startup_method": "claude_cli",  # claude_cli, docker, custom_script
        "startup_command": "claude --name {agent_id} --role {agent_type} --sub-agent",  # MainAgentが指定
        "environment_vars": {  # MainAgentが指定する環境変数
            "CUSTOM_VAR": "value",
            "PROJECT_NAME": "myproject"
        },
        "config": {
            "role": "tester",
            "mode": "test"
        }
    }
    """
    try:
        requester_agent_id = data.get("requester_agent_id")
        agent_type = data.get("agent_type")
        agent_id = data.get("agent_id", f"{agent_type}_agent")
        working_directory = data.get("working_directory", ".")
        launch_mode = data.get("launch_mode", "agent")

        # MainAgentが指定する起動方法
        startup_method = data.get("startup_method", "claude_cli")  # デフォルトはClaude CLI
        custom_startup_command = data.get("startup_command")  # MainAgentが指定するコマンド
        custom_env_vars = data.get("environment_vars", {})  # 追加環境変数

        config = data.get("config", {})

        log.info(
            f"Agent start request from {requester_agent_id}: {agent_type}:{agent_id} via {startup_method}"
        )

        # 新しいターミナルセッションを作成
        session_id = str(uuid4())

        # エージェント設定に起動情報を追加
        agent_config = {
            "agent_type": agent_type,
            "agent_id": agent_id,
            "working_directory": working_directory,
            "startup_method": startup_method,
            "custom_startup_command": custom_startup_command,
            "custom_environment_vars": custom_env_vars,
            "requester_agent_id": requester_agent_id,
            **config,
        }

        # create_terminal関数を呼び出してエージェント用ターミナルを作成
        await create_terminal(
            sid,
            {
                "session": session_id,
                "path": working_directory,
                "launch_mode": launch_mode,
                "agent_config": agent_config,
                "requester_agent_id": requester_agent_id,
            },
        )

        log.info(
            f"Agent start request processed: session {session_id} created for {agent_type}:{agent_id}"
        )

    except Exception as e:
        log.error(f"Error handling agent start request: {e}")
        await sio_instance.emit(
            "agent_message",
            {
                "message_type": "agent_start_response",
                "requester_agent_id": data.get("requester_agent_id"),
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


async def spec_upload(sid, data):
    """
    エージェント向け仕様ドキュメントのアップロード・配信

    メッセージフォーマット:
    {
        "from_agent_id": "claude_main_001",
        "spec_type": "project_requirements",  # project_requirements, api_spec, design_doc, user_story
        "title": "ユーザー認証システム仕様",
        "content": "...",  # 仕様内容
        "target_agents": ["claude_dev_001", "claude_test_001"],  # 対象エージェント（空の場合は全員）
        "priority": "high",
        "format": "markdown",  # markdown, json, yaml, plain
        "metadata": {
            "version": "1.0",
            "author": "Product Manager",
            "last_updated": "2025-01-29"
        }
    }
    """
    try:
        from_agent_id = data.get("from_agent_id")
        spec_type = data.get("spec_type")
        title = data.get("title")
        content = data.get("content")
        target_agents = data.get("target_agents", [])  # 空の場合は全エージェント
        priority = data.get("priority", "medium")
        format_type = data.get("format", "markdown")
        metadata = data.get("metadata", {})

        log.info(f"Spec upload from {from_agent_id}: {spec_type} - {title}")

        # 仕様ドキュメントをベクトルストレージに保存（検索可能にする）
        try:
            from aetherterm.langchain.storage.vector_adapter import VectorStorageAdapter
            # TODO: VectorStorageAdapterへの保存実装
        except ImportError:
            log.warning("VectorStorageAdapter not available for spec storage")

        # 全エージェントまたは指定エージェントに配信
        await sio_instance.emit(
            "agent_message",
            {
                "message_type": "spec_document",
                "from_agent_id": from_agent_id,
                "target_agents": target_agents,
                "spec_type": spec_type,
                "title": title,
                "content": content,
                "priority": priority,
                "format": format_type,
                "metadata": metadata,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        log.info(
            f"Spec document '{title}' distributed to {len(target_agents) if target_agents else 'all'} agents"
        )

    except Exception as e:
        log.error(f"Error handling spec upload: {e}")
        await sio_instance.emit("error", {"message": f"Spec upload failed: {e!s}"}, room=sid)


async def spec_query(sid, data):
    """
    エージェントによる仕様問い合わせ

    メッセージフォーマット:
    {
        "from_agent_id": "claude_dev_001",
        "query": "ユーザー認証のAPIエンドポイント仕様は？",
        "spec_types": ["api_spec", "project_requirements"],  # 検索対象の仕様タイプ
        "context": "現在LoginForm.vueの実装中"
    }
    """
    try:
        from_agent_id = data.get("from_agent_id")
        query = data.get("query")
        spec_types = data.get("spec_types", [])
        context = data.get("context", "")

        log.info(f"Spec query from {from_agent_id}: {query}")

        # TODO: ベクトル検索で関連仕様を取得
        # 現在はモックレスポンス
        search_results = [
            {
                "title": "ユーザー認証API仕様",
                "spec_type": "api_spec",
                "content": "POST /api/auth/login - ユーザーログイン処理...",
                "relevance_score": 0.95,
            }
        ]

        # 検索結果を返信
        await sio_instance.emit(
            "agent_message",
            {
                "message_type": "spec_query_response",
                "to_agent_id": from_agent_id,
                "query": query,
                "results": search_results,
                "total_results": len(search_results),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    except Exception as e:
        log.error(f"Error handling spec query: {e}")
        await sio_instance.emit("error", {"message": f"Spec query failed: {e!s}"}, room=sid)


async def control_message(sid, data):
    """
    システム制御メッセージを処理

    メッセージフォーマット:
    {
        "from_agent_id": "claude_main_001",
        "control_type": "pause_all",  # pause_all, resume_all, shutdown_agent, restart_agent
        "target_agent_id": "claude_tester_001",  # 特定エージェント対象の場合
        "data": {}
    }
    """
    try:
        from_agent_id = data.get("from_agent_id")
        control_type = data.get("control_type")
        target_agent_id = data.get("target_agent_id")
        control_data = data.get("data", {})

        log.info(
            f"Control message from {from_agent_id}: {control_type} -> {target_agent_id or 'all'}"
        )

        # システム制御メッセージをブロードキャスト
        await sio_instance.emit(
            "agent_message",
            {
                "message_type": "control_message",
                "from_agent_id": from_agent_id,
                "control_type": control_type,
                "target_agent_id": target_agent_id,
                "data": control_data,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    except Exception as e:
        log.error(f"Error handling control message: {e}")
        await sio_instance.emit("error", {"message": f"Control message failed: {e!s}"}, room=sid)


def _get_agent_capabilities(agent_type: str) -> list:
    """
    エージェントタイプ別の能力一覧を取得
    """
    capabilities_map = {
        "developer": [
            "code_generation",
            "debugging",
            "refactoring",
            "api_implementation",
            "frontend_development",
            "backend_development",
            "git_operations",
        ],
        "reviewer": [
            "code_review",
            "security_analysis",
            "performance_analysis",
            "best_practices_check",
            "documentation_review",
            "test_coverage_analysis",
        ],
        "tester": [
            "test_generation",
            "unit_testing",
            "integration_testing",
            "e2e_testing",
            "test_automation",
            "bug_reporting",
            "test_coverage_measurement",
        ],
        "architect": [
            "system_design",
            "architecture_analysis",
            "technology_selection",
            "scalability_planning",
            "database_design",
            "api_design",
            "documentation_generation",
        ],
        "researcher": [
            "information_gathering",
            "technology_research",
            "best_practices_research",
            "competitive_analysis",
            "documentation_analysis",
            "trend_analysis",
        ],
    }

    return capabilities_map.get(agent_type, ["general_assistance"])


def _get_agent_instructions(agent_type: str, parent_agent_id: str = None) -> dict:
    """
    エージェントタイプ別の初期指示を取得
    """
    base_instructions = {
        "role_description": f"You are a {agent_type} agent in the AetherTerm platform.",
        "hierarchy_info": "You are a sub-agent" if parent_agent_id else "You are a main agent",
        "communication_protocol": {
            "websocket_events": ["agent_message", "spec_query", "control_message"],
            "message_filtering": "Filter messages by to_agent_id or process broadcasts",
            "parent_communication": f"Report to parent agent: {parent_agent_id}"
            if parent_agent_id
            else None,
        },
        "server_integration": {
            "websocket_url": "ws://localhost:57575",
            "api_base": "http://localhost:57575/api/v1",
            "spec_query_endpoint": "/api/v1/specs/query",
            "agent_status_endpoint": "/api/v1/agents/status",
        },
    }

    type_specific_instructions = {
        "developer": {
            "primary_tasks": [
                "Implement features based on specifications",
                "Write clean, maintainable code",
                "Follow coding standards and best practices",
                "Collaborate with other agents for reviews and testing",
            ],
            "collaboration_pattern": [
                "Request code reviews from reviewer agents",
                "Coordinate with tester agents for test cases",
                "Consult architect agents for design decisions",
            ],
        },
        "reviewer": {
            "primary_tasks": [
                "Review code for quality and security",
                "Provide constructive feedback",
                "Ensure compliance with standards",
                "Identify potential issues and improvements",
            ],
            "collaboration_pattern": [
                "Respond to review requests from developer agents",
                "Coordinate with architect agents for design reviews",
                "Work with tester agents on test strategy",
            ],
        },
        "tester": {
            "primary_tasks": [
                "Generate comprehensive test cases",
                "Execute automated and manual tests",
                "Report bugs and issues",
                "Measure and improve test coverage",
            ],
            "collaboration_pattern": [
                "Coordinate with developer agents for test requirements",
                "Work with reviewer agents on test strategies",
                "Report findings to all relevant agents",
            ],
        },
        "architect": {
            "primary_tasks": [
                "Design system architecture",
                "Make technology decisions",
                "Create technical documentation",
                "Guide implementation decisions",
            ],
            "collaboration_pattern": [
                "Provide guidance to developer agents",
                "Collaborate with reviewer agents on design reviews",
                "Work with researcher agents on technology selection",
            ],
        },
        "researcher": {
            "primary_tasks": [
                "Research technologies and best practices",
                "Analyze requirements and constraints",
                "Provide recommendations",
                "Gather relevant documentation",
            ],
            "collaboration_pattern": [
                "Provide research findings to all agent types",
                "Support architect agents with technology analysis",
                "Assist developer agents with implementation research",
            ],
        },
    }

    base_instructions.update(type_specific_instructions.get(agent_type, {}))

    # 親エージェントがいる場合の追加指示
    if parent_agent_id:
        base_instructions["parent_agent_communication"] = {
            "reporting_schedule": "Report progress regularly to parent agent",
            "escalation_rules": "Escalate blocking issues to parent agent",
            "completion_notification": "Notify parent agent when tasks are completed",
            "parent_agent_id": parent_agent_id,
        }

    return base_instructions


async def agent_hello(sid, data):
    """
    エージェントからの初期接続メッセージを処理

    メッセージフォーマット:
    {
        "agent_id": "claude_dev_001",
        "agent_type": "developer",
        "version": "1.0.0",
        "capabilities": [...],
        "request_initialization": true
    }
    """
    try:
        agent_id = data.get("agent_id")
        agent_type = data.get("agent_type")
        version = data.get("version", "unknown")
        capabilities = data.get("capabilities", [])

        log.info(f"Agent hello from {agent_id} ({agent_type}) version {version}")

        # エージェント情報を登録/更新
        agent_info = {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "version": version,
            "capabilities": capabilities,
            "status": "connected",
            "connected_at": datetime.utcnow().isoformat(),
            "last_seen": datetime.utcnow().isoformat(),
        }

        # エージェント情報をグローバルストレージに保存（TODO: 実装）
        # store_agent_info(agent_id, agent_info)

        # 既存のターミナルセッションからエージェント情報を取得
        parent_agent_id = None
        agent_hierarchy = "main"

        # ターミナルセッションからエージェント設定を検索
        from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import (
            AsyncioTerminal,
        )

        for session_id, terminal in AsyncioTerminal.sessions.items():
            if hasattr(terminal, "agent_config") and terminal.agent_config:
                agent_config = terminal.agent_config.get("agent_config", {})
                if agent_config.get("agent_id") == agent_id:
                    parent_agent_id = terminal.agent_config.get("parent_agent_id")
                    agent_hierarchy = terminal.agent_config.get("agent_hierarchy", "main")
                    break

        # エージェントに初期化情報を送信
        await sio_instance.emit(
            "agent_message",
            {
                "message_type": "agent_initialization",
                "to_agent_id": agent_id,
                "agent_info": {
                    "agent_id": agent_id,
                    "agent_type": agent_type,
                    "role": "sub_agent" if parent_agent_id else "main_agent",
                    "hierarchy": agent_hierarchy,
                    "parent_agent_id": parent_agent_id,
                    "server_info": {
                        "websocket_url": "ws://localhost:57575",
                        "rest_api_base": "http://localhost:57575/api/v1",
                    },
                    "capabilities": _get_agent_capabilities(agent_type),
                    "instructions": _get_agent_instructions(agent_type, parent_agent_id),
                },
                "welcome_message": f"Welcome {agent_id}! You are a {agent_hierarchy} {agent_type} agent.",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        # 他のエージェントに新しいエージェントの参加を通知
        await sio_instance.emit(
            "agent_message",
            {
                "message_type": "agent_joined",
                "agent_info": {
                    "agent_id": agent_id,
                    "agent_type": agent_type,
                    "hierarchy": agent_hierarchy,
                    "capabilities": capabilities,
                },
                "announcement": f"Agent {agent_id} ({agent_type}) has joined the workspace.",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    except Exception as e:
        log.error(f"Error handling agent hello: {e}")
        await sio_instance.emit("error", {"message": f"Agent hello failed: {e!s}"}, room=sid)


async def wrapper_session_sync(sid, data):
    """Handle session synchronization from wrapper programs."""
    try:
        action = data.get("action")
        wrapper_info = data.get("wrapper_info", {})

        log.info(f"Wrapper session sync received: {action} from PID {wrapper_info.get('pid')}")

        if action == "bulk_sync":
            # 複数セッションの一括同期
            sessions = data.get("sessions", [])
            log.info(f"Bulk sync: {len(sessions)} sessions from wrapper")

            # フロントエンドに同期情報を送信
            await sio_instance.emit(
                "wrapper_sessions_update",
                {
                    "action": "bulk_sync",
                    "sessions": sessions,
                    "wrapper_info": wrapper_info,
                    "timestamp": data.get("timestamp"),
                },
            )

        elif action in ["created", "updated", "closed"]:
            # 単一セッションの同期
            session = data.get("session", {})
            session_id = session.get("session_id")

            log.debug(f"Session {action}: {session_id}")

            # フロントエンドに同期情報を送信
            await sio_instance.emit(
                "wrapper_session_update",
                {
                    "action": action,
                    "session": session,
                    "wrapper_info": wrapper_info,
                    "timestamp": data.get("timestamp"),
                },
            )

        # 同期完了の応答を送信
        await sio_instance.emit(
            "wrapper_session_sync_response",
            {"status": "success", "action": action, "timestamp": data.get("timestamp")},
            room=sid,
        )

    except Exception as e:
        log.error(f"Error handling wrapper session sync: {e}")
        await sio_instance.emit(
            "wrapper_session_sync_response", {"status": "error", "error": str(e)}, room=sid
        )


async def get_wrapper_sessions(sid, data):
    """Handle request for wrapper session information."""
    try:
        # この機能は将来的にWrapperセッション情報を取得するために使用
        # 現在は基本的な応答のみ
        await sio_instance.emit(
            "wrapper_sessions_response",
            {"status": "success", "message": "Wrapper session information request received"},
            room=sid,
        )
    except Exception as e:
        log.error(f"Error getting wrapper sessions: {e}")
        await sio_instance.emit(
            "wrapper_sessions_response", {"status": "error", "error": str(e)}, room=sid
        )


async def log_monitor_subscribe(sid, data):
    """Subscribe to log monitoring updates."""
    try:
        terminal_id = data.get("terminal_id")
        log.info(f"Client {sid} subscribing to log monitor for terminal {terminal_id}")

        # Join log monitoring room
        await sio_instance.enter_room(sid, f"log_monitor_{terminal_id}")

        if log_processing_manager:
            # Get current statistics
            stats = await log_processing_manager.get_terminal_statistics(terminal_id)
            await sio_instance.emit(
                "log_monitor_stats", {"terminal_id": terminal_id, "stats": stats}, room=sid
            )

        await sio_instance.emit(
            "log_monitor_subscribed", {"status": "success", "terminal_id": terminal_id}, room=sid
        )
    except Exception as e:
        log.error(f"Error subscribing to log monitor: {e}")
        await sio_instance.emit("log_monitor_error", {"error": str(e)}, room=sid)


async def log_monitor_unsubscribe(sid, data):
    """Unsubscribe from log monitoring updates."""
    try:
        terminal_id = data.get("terminal_id")
        log.info(f"Client {sid} unsubscribing from log monitor for terminal {terminal_id}")

        # Leave log monitoring room
        await sio_instance.leave_room(sid, f"log_monitor_{terminal_id}")

        await sio_instance.emit(
            "log_monitor_unsubscribed", {"status": "success", "terminal_id": terminal_id}, room=sid
        )
    except Exception as e:
        log.error(f"Error unsubscribing from log monitor: {e}")


async def log_monitor_search(sid, data):
    """Handle log search requests."""
    try:
        query = data.get("query", "")
        terminal_id = data.get("terminal_id")
        limit = data.get("limit", 100)

        if log_processing_manager:
            results = await log_processing_manager.search_logs(
                query=query, terminal_id=terminal_id, limit=limit
            )

            await sio_instance.emit(
                "log_search_results",
                {
                    "query": query,
                    "terminal_id": terminal_id,
                    "results": results,
                    "count": len(results),
                },
                room=sid,
            )
        else:
            await sio_instance.emit(
                "log_search_results",
                {
                    "query": query,
                    "terminal_id": terminal_id,
                    "results": [],
                    "count": 0,
                    "error": "Log processing manager not available",
                },
                room=sid,
            )
    except Exception as e:
        log.error(f"Error handling log search: {e}")
        await sio_instance.emit("log_search_error", {"error": str(e)}, room=sid)


# Event-driven log statistics broadcasting
_log_stats_task = None
_log_stats_interval = 5  # seconds


async def broadcast_log_statistics():
    """Broadcast log statistics to all subscribed clients via event-driven approach."""
    global _log_stats_task

    try:
        # Skip log statistics for now to avoid DI issues
        if sio_instance:
            # Send empty stats to avoid errors
            system_stats = {"total_logs": 0, "error_count": 0, "processing_active": False}

            # Broadcast to all log monitor subscribers
            await sio_instance.emit(
                "log_system_stats",
                {"stats": system_stats, "timestamp": asyncio.get_event_loop().time()},
                namespace="/",
            )

    except Exception as e:
        log.error(f"Error broadcasting log statistics: {e}")

    # Schedule next broadcast
    if _log_stats_task and not _log_stats_task.cancelled():
        _log_stats_task = asyncio.create_task(_schedule_next_broadcast())


async def _schedule_next_broadcast():
    """Schedule the next statistics broadcast."""
    await asyncio.sleep(_log_stats_interval)
    await broadcast_log_statistics()


def start_log_monitoring_background_task():
    """Start the background task for log monitoring with Pub/Sub."""
    global _log_stats_task

    if sio_instance:
        # Start the initial broadcast
        _log_stats_task = asyncio.create_task(broadcast_log_statistics())
        # Pub/Subリスナーも開始
        asyncio.create_task(start_redis_pubsub_listener())


def stop_log_monitoring_background_task():
    """Stop the log monitoring background task."""
    global _log_stats_task

    if _log_stats_task and not _log_stats_task.cancelled():
        _log_stats_task.cancel()
        _log_stats_task = None


async def start_redis_pubsub_listener():
    """
    Redis Pub/Subリスナーを開始してリアルタイムアップデートを受信
    """
    try:
        from aetherterm.logprocessing.log_processing_manager import get_log_processing_manager

        manager = get_log_processing_manager()
        if not manager or not manager.redis_storage:
            log.warning("Redis storage not available for Pub/Sub")
            return

        # リアルタイムイベント用チャンネル
        patterns = ["terminal:input:*", "terminal:output:*", "terminal:error:*", "system:events"]

        await manager.redis_storage.subscribe_with_pattern(
            patterns=patterns, callback=handle_realtime_log_event
        )

    except Exception as e:
        log.error(f"Failed to start Redis Pub/Sub listener: {e}")


async def handle_realtime_log_event(channel: str, message: str):
    """
    Redis Pub/SubメッセージをWebSocketクライアントにブロードキャスト
    """
    try:
        import json

        data = json.loads(message)

        # チャンネルによって処理を分岐
        if "terminal:error:" in channel:
            # エラーイベントを緊急通知
            await sio_instance.emit(
                "terminal_error_alert",
                {
                    "terminal_id": data.get("terminal_id"),
                    "error_data": data.get("data", {}),
                    "timestamp": data.get("timestamp"),
                    "severity": data.get("data", {})
                    .get("processed_data", {})
                    .get("severity", "unknown"),
                },
            )

        elif "terminal:input:" in channel:
            # コマンド入力イベント
            await sio_instance.emit(
                "terminal_command_executed",
                {
                    "terminal_id": data.get("terminal_id"),
                    "command": data.get("data", {}).get("processed_data", {}).get("command", ""),
                    "timestamp": data.get("timestamp"),
                },
            )

        elif "system:events" in channel:
            # システムイベント
            if data.get("type") == "error_detected":
                await sio_instance.emit(
                    "system_error_alert",
                    {
                        "terminal_id": data.get("terminal_id"),
                        "severity": data.get("severity"),
                        "timestamp": data.get("timestamp"),
                    },
                )

        # 全体統計を更新
        await update_and_broadcast_statistics()

    except Exception as e:
        log.error(f"Error handling realtime log event: {e}")


async def update_and_broadcast_statistics():
    """統計情報を更新してブロードキャスト"""
    try:
        # Send empty stats for now to avoid DI issues
        stats = {"total_logs": 0, "error_count": 0, "processing_active": False}

        if sio_instance:
            await sio_instance.emit("log_system_stats", {"stats": stats})

    except Exception as e:
        log.error(f"Error updating statistics: {e}")


def get_terminal_context(session_id):
    """Extract terminal context for AI assistance."""
    if session_id and session_id in AsyncioTerminal.sessions:
        terminal = AsyncioTerminal.sessions[session_id]
        context_parts = []

        # Add terminal history if available
        if hasattr(terminal, "history") and terminal.history:
            # Get last 1000 characters of terminal history to avoid overwhelming the AI
            recent_history = (
                terminal.history[-1000:] if len(terminal.history) > 1000 else terminal.history
            )
            context_parts.append(f"Recent terminal output:\n{recent_history}")

        # Add current working directory if available
        if hasattr(terminal, "path") and terminal.path:
            context_parts.append(f"Current directory: {terminal.path}")

        # Add user information if available
        if hasattr(terminal, "user") and terminal.user:
            context_parts.append(f"User: {terminal.user.name}")

        return "\n\n".join(context_parts) if context_parts else None

    return None


async def send_terminal_history(sid, session_id, terminal):
    """Send terminal history to a client - centralizes history sending logic."""
    try:
        # Use persistent buffer if available
        buffer_content = AsyncioTerminal.get_session_buffer_content(session_id)

        if buffer_content:
            log.info(
                f"Sending persistent buffer content to client {sid} for session {session_id}, length: {len(buffer_content)}"
            )
            await sio_instance.emit(
                "terminal_output",
                {"session": session_id, "data": buffer_content},
                room=sid,
            )
        elif hasattr(terminal, "history") and terminal.history:
            # Fallback to in-memory history if persistent buffer is empty
            log.info(
                f"Sending in-memory history to client {sid} for session {session_id}, length: {len(terminal.history)}"
            )
            await sio_instance.emit(
                "terminal_output",
                {"session": session_id, "data": terminal.history},
                room=sid,
            )
        else:
            log.warning(f"No buffer content or history available for session {session_id}")
    except Exception as e:
        log.error(f"Error sending terminal history: {e}")


# AI Chat and Log Search Handlers


async def reconnect_session(sid, data):
    """Handle session reconnection request."""
    try:
        session_id = data.get("session")

        if not session_id:
            log.warning("Reconnect session request without session ID")
            await sio_instance.emit(
                "session_not_found",
                {"session": session_id, "error": "Session ID required"},
                room=sid,
            )
            return

        log.info(f"Session reconnection request for {session_id} from client {sid}")

        # Check if session exists
        if session_id in AsyncioTerminal.sessions:
            terminal = AsyncioTerminal.sessions[session_id]

            if not terminal.closed:
                # Session is active - send success response
                log.info(f"Reconnecting to active session {session_id}")

                # Add client to session
                terminal.client_sids.add(sid)

                # Send reconnection success - client expects terminal_ready
                await sio_instance.emit(
                    "terminal_ready", {"session": session_id, "status": "ready"}, room=sid
                )

                # Send terminal history/buffer content
                await send_terminal_history(sid, session_id, terminal)

                return
            else:
                # Session exists but is closed
                log.info(f"Session {session_id} exists but is closed")

        # Session not found or closed
        log.info(f"Session {session_id} not found or closed")
        await sio_instance.emit("session_not_found", {"session": session_id}, room=sid)

    except Exception as e:
        log.error(f"Error handling reconnect session: {e}", exc_info=True)
        await sio_instance.emit(
            "session_not_found",
            {"session": session_id if "session_id" in locals() else None, "error": str(e)},
            room=sid,
        )


# ========================================
# Workspace Management Event Handlers
# ========================================


async def on_workspace_connect(sid, data):
    """Handle user connection to the global workspace."""
    try:
        from aetherterm.agentserver.domain.services.global_workspace_service import (
            get_global_workspace_service,
        )

        service = get_global_workspace_service()

        # Get user info from environment to extract role
        environ = getattr(sio_instance, "environ", {}) if sio_instance else {}
        user_info = get_user_info_from_environ(environ)

        # Extract role from user info
        user_roles = user_info.get("roles", [])

        # Determine role: if "Viewer" is in roles, use that, otherwise default to "User"
        role = "Viewer" if "Viewer" in user_roles else "User"

        # Allow override from data if provided
        if "role" in data:
            role = data["role"]

        # Add user to global workspace
        service.add_user(sid, role)

        log.info(f"User {sid} ({role}) connected to global workspace with roles: {user_roles}")

        await sio_instance.emit("workspace_connected", {"success": True, "role": role}, room=sid)

    except Exception as e:
        log.error(f"Error connecting to workspace: {e}", exc_info=True)
        await sio_instance.emit("workspace_error", {"error": str(e)}, room=sid)


async def on_workspace_create(sid, data):
    """Create workspace - returns the global workspace since we can't create new workspaces."""
    try:
        from aetherterm.agentserver.domain.services.global_workspace_service import (
            get_global_workspace_service,
        )

        service = get_global_workspace_service()

        # Check if user has permission to modify
        if not service.can_user_modify(sid):
            log.warning(f"User {sid} (Viewer) attempted to create workspace")
            await sio_instance.emit(
                "workspace_error", {"error": "Viewers cannot create workspaces"}, room=sid
            )
            return

        # We only have one global workspace, so return it
        workspace = service.get_workspace()

        log.info(f"User {sid} requested workspace creation - returning global workspace")

        await sio_instance.emit(
            "workspace_created", {"success": True, "workspace": workspace}, room=sid
        )

    except Exception as e:
        log.error(f"Error in workspace create handler: {e}", exc_info=True)
        await sio_instance.emit("workspace_error", {"error": str(e)}, room=sid)


async def on_workspace_update(sid, data):
    """Update the global workspace."""
    try:
        from aetherterm.agentserver.domain.services.global_workspace_service import (
            get_global_workspace_service,
        )

        service = get_global_workspace_service()

        # Check if user has permission to modify
        if not service.can_user_modify(sid):
            log.warning(f"User {sid} (Viewer) attempted to update workspace")
            await sio_instance.emit(
                "workspace_error", {"error": "Viewers cannot modify the workspace"}, room=sid
            )
            return

        workspace_data = data.get("workspaceData", {})

        # Update the global workspace
        updated_workspace = service.update_workspace(workspace_data)

        log.info(f"User {sid} updated global workspace")

        await sio_instance.emit(
            "workspace_updated", {"success": True, "workspace": updated_workspace}, room=sid
        )

        # Broadcast update to all connected users
        await sio_instance.emit(
            "workspace_changed",
            {"workspace": updated_workspace},
            skip_sid=sid,  # Don't send to the user who made the change
        )

    except Exception as e:
        log.error(f"Error updating workspace: {e}", exc_info=True)
        await sio_instance.emit("workspace_error", {"error": str(e)}, room=sid)


async def on_tab_create(sid, data):
    """Create a new tab in the global workspace."""
    try:
        from aetherterm.agentserver.domain.services.global_workspace_service import (
            get_global_workspace_service,
        )

        service = get_global_workspace_service()

        # Check if user has permission to modify
        if not service.can_user_modify(sid):
            log.warning(f"User {sid} (Viewer) attempted to create tab")
            await sio_instance.emit(
                "workspace_error", {"error": "Viewers cannot create tabs"}, room=sid
            )
            return

        title = data.get("title", "New Tab")
        tab_type = data.get("type", "terminal")
        sub_type = data.get("subType")

        # Create tab in the global workspace
        tab = service.create_tab(title, tab_type, sub_type)

        if tab:
            # For terminal tabs, automatically create the terminal session
            if tab_type == "terminal" and tab["panes"]:
                for pane in tab["panes"]:
                    pane_id = pane["id"]
                    session_id = f"terminal_{pane_id}_{uuid4().hex[:8]}"

                    # Create terminal session
                    await create_terminal(
                        sid,
                        {
                            "session": session_id,
                            "tabId": tab["id"],
                            "paneId": pane_id,
                            "subType": sub_type or "pure",
                            "type": "terminal",
                            "cols": 80,
                            "rows": 24,
                        },
                    )

                    # Update pane with session ID
                    service.update_pane_session(tab["id"], pane_id, session_id)
                    pane["sessionId"] = session_id

            log.info(f"User {sid} created tab {tab['id']} in global workspace")

            await sio_instance.emit("tab_created", {"success": True, "tab": tab}, room=sid)

            # Broadcast tab creation to all connected users
            await sio_instance.emit(
                "tab_added",
                {"tab": tab},
                skip_sid=sid,  # Don't send to the user who created it
            )
        else:
            await sio_instance.emit(
                "workspace_error",
                {"error": "Failed to create tab - maximum tabs reached"},
                room=sid,
            )

    except Exception as e:
        log.error(f"Error creating tab: {e}", exc_info=True)
        await sio_instance.emit("workspace_error", {"error": str(e)}, room=sid)

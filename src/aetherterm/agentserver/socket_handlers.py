import asyncio
import logging
from uuid import uuid4

from dependency_injector.wiring import Provide, inject

from aetherterm.agentserver import utils
from aetherterm.agentserver.ai_services import get_ai_service
from aetherterm.agentserver.auto_blocker import (
    BlockReason,
    get_auto_blocker,
    set_socket_io_instance,
)
from aetherterm.agentserver.containers import ApplicationContainer
from aetherterm.agentserver.log_analyzer import SeverityLevel, get_log_analyzer
from aetherterm.agentserver.terminals.asyncio_terminal import AsyncioTerminal
from aetherterm.agentserver.utils import User
from aetherterm.common.agent_protocol import PaneConfig, PaneType

log = logging.getLogger("aetherterm.socket_handlers")

# Global storage for socket.io server instance
sio_instance = None
# Global pane manager instance
_pane_manager = None
# ZMQ instances (None when ZMQ disabled)
_zmq_broker = None
_zmq_bridge = None


def set_sio_instance(sio):
    """Set the global socket.io server instance."""
    global sio_instance
    sio_instance = sio
    # 自動ブロッカーにSocket.IOインスタンスを設定
    set_socket_io_instance(sio)


def set_pane_manager(pane_manager):
    """Set the global pane manager instance."""
    global _pane_manager
    _pane_manager = pane_manager


def set_zmq_broker(broker):
    """Set the global ZMQ broker instance (None when ZMQ disabled)."""
    global _zmq_broker
    _zmq_broker = broker


def set_zmq_bridge(bridge):
    """Set the global ZMQ bridge instance (None when ZMQ disabled)."""
    global _zmq_bridge
    _zmq_bridge = bridge


def get_user_info_from_environ(environ):
    """Extract user information from environment/headers."""
    user_info = {
        "remote_addr": environ.get("REMOTE_ADDR"),
        "remote_user": environ.get("HTTP_X_REMOTE_USER"),
        "forwarded_for": environ.get("HTTP_X_FORWARDED_FOR"),
        "user_agent": environ.get("HTTP_USER_AGENT"),
    }
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


import jinja2


@inject
async def connect(
    sid,
    environ,
    config_motd: str = Provide[ApplicationContainer.config.motd],
):
    """Handle client connection."""
    log.info(f"Client connected: {sid}")
    await sio_instance.emit("connected", {"data": "Connected to Butterfly"}, room=sid)

    try:
        with open(config_motd) as f:
            motd_content = f.read()

        # Jinja2 rendering
        template = jinja2.Template(motd_content)
        rendered_motd = template.render()

        await sio_instance.emit(
            "terminal_output", {"session": "motd", "data": rendered_motd}, room=sid
        )
    except FileNotFoundError:
        log.warning(f"MOTD file not found: {config_motd}")
    except Exception as e:
        log.error(f"Error reading MOTD file: {e}")


async def disconnect(sid, environ=None):
    """Handle client disconnection."""
    log.info(f"Client disconnected: {sid}")

    # Remove client from any terminal sessions and close if no clients remain
    for session_id, terminal in list(AsyncioTerminal.sessions.items()):
        if hasattr(terminal, "client_sids") and sid in terminal.client_sids:
            terminal.client_sids.discard(sid)
            log.info(f"Removed client {sid} from terminal session {session_id}")
            # If no clients remain, close the terminal
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
    try:
        session_id = data.get("session", str(uuid4()))
        user_name = data.get("user", "")
        path = data.get("path", "")

        # Check if this is a request for a specific session (not a new random one)
        is_specific_session_request = "session" in data and data["session"] != ""

        log.info(f"Creating terminal session {session_id} for client {sid}")
        log.debug(f"Terminal data: user={user_name}, path={path}")

        # Check if session already exists and is still active
        if session_id in AsyncioTerminal.sessions:
            existing_terminal = AsyncioTerminal.sessions[session_id]
            if not existing_terminal.closed:
                log.info(f"Reusing existing terminal session {session_id}")
                # Add this client to the existing terminal's client set
                existing_terminal.client_sids.add(sid)
                # Send terminal history to new client
                if existing_terminal.history:
                    await sio_instance.emit(
                        "terminal_output",
                        {"session": session_id, "data": existing_terminal.history},
                        room=sid,
                    )
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

        # Create terminal instance directly (not using factory since it has issues)
        log.debug("Creating AsyncioTerminal instance")
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

        # Associate terminal with client using the new client set
        terminal_instance.client_sids.add(sid)

        # Start the PTY
        log.debug("Starting PTY")
        await terminal_instance.start_pty()
        log.info(f"PTY started successfully for session {session_id}")

        # Notify client that terminal is ready
        await sio_instance.emit(
            "terminal_ready", {"session": session_id, "status": "ready"}, room=sid
        )
        log.debug(f"Sent terminal_ready event to client {sid}")

    except Exception as e:
        log.error(f"Error creating terminal: {e}", exc_info=True)
        await sio_instance.emit("terminal_error", {"error": str(e)}, room=sid)


async def terminal_input(sid, data):
    """Handle input from client to terminal."""
    try:
        session_id = data.get("session")
        input_data = data.get("data", "")

        if session_id in AsyncioTerminal.sessions:
            terminal = AsyncioTerminal.sessions[session_id]
            await terminal.write(input_data)

            # ZMQ: Forward terminal input to ZMQ PUB/SUB for agent monitoring
            if _zmq_bridge and _zmq_bridge.is_running:
                asyncio.create_task(
                    _zmq_bridge.forward_terminal_input_to_zmq(session_id, input_data)
                )
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


def broadcast_to_session(session_id, message):
    """Broadcast message to all clients connected to a session."""
    if sio_instance:
        import asyncio

        # Get the terminal to find connected clients
        terminal = AsyncioTerminal.sessions.get(session_id)
        if terminal and hasattr(terminal, "client_sids"):
            client_sids = list(terminal.client_sids)
        else:
            client_sids = []

        if message is not None:
            # リアルタイムログ解析を実行
            log_analyzer = get_log_analyzer()
            auto_blocker = get_auto_blocker()

            detection_result = log_analyzer.analyze_output(session_id, message)

            if detection_result and detection_result.should_block:
                # 危険検出時の自動ブロック
                block_reason = (
                    BlockReason.CRITICAL_KEYWORD
                    if detection_result.severity == SeverityLevel.CRITICAL
                    else BlockReason.MULTIPLE_WARNINGS
                )

                success = auto_blocker.block_session(
                    session_id=session_id,
                    reason=block_reason,
                    message=detection_result.message,
                    alert_message=detection_result.alert_message,
                    detected_keywords=detection_result.detected_keywords,
                )

                if success:
                    log.warning(
                        f"Session {session_id} automatically blocked due to: {detection_result.message}"
                    )

            # Terminal output - broadcast to all clients in this session
            log.debug(
                f"Broadcasting terminal output for session {session_id} to {len(client_sids)} clients: {message!r}"
            )
            for client_sid in client_sids:
                asyncio.create_task(
                    sio_instance.emit(
                        "terminal_output", {"session": session_id, "data": message}, room=client_sid
                    )
                )

            # ZMQ: Forward terminal output to ZMQ PUB/SUB for agent monitoring
            if _zmq_bridge and _zmq_bridge.is_running:
                asyncio.create_task(_zmq_bridge.forward_terminal_output_to_zmq(session_id, message))
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
        log.error(f"Error handling wrapper sessions request: {e}")
        await sio_instance.emit(
            "wrapper_sessions_response", {"status": "error", "error": str(e)}, room=sid
        )


async def unblock_request(sid, data):
    """Handle unblock request from client."""
    try:
        session_id = data.get("session_id")
        unlock_key = data.get("unlock_key", "ctrl_d")

        if not session_id:
            log.warning("Unblock request without session_id")
            await sio_instance.emit(
                "unblock_response", {"status": "error", "error": "session_id required"}, room=sid
            )
            return

        auto_blocker = get_auto_blocker()
        success = auto_blocker.unblock_session(session_id, unlock_key)

        if success:
            await sio_instance.emit(
                "unblock_response",
                {
                    "status": "success",
                    "session_id": session_id,
                    "message": "ブロックが解除されました",
                },
                room=sid,
            )
            log.info(f"Session {session_id} unblocked by client {sid}")
        else:
            await sio_instance.emit(
                "unblock_response",
                {
                    "status": "error",
                    "session_id": session_id,
                    "error": "ブロック解除に失敗しました",
                },
                room=sid,
            )

    except Exception as e:
        log.error(f"Error handling unblock request: {e}")
        await sio_instance.emit("unblock_response", {"status": "error", "error": str(e)}, room=sid)


async def get_block_status(sid, data):
    """Handle block status request from client."""
    try:
        session_id = data.get("session_id")

        if not session_id:
            log.warning("Block status request without session_id")
            await sio_instance.emit(
                "block_status_response",
                {"status": "error", "error": "session_id required"},
                room=sid,
            )
            return

        auto_blocker = get_auto_blocker()
        is_blocked = auto_blocker.is_session_blocked(session_id)
        block_state = auto_blocker.get_block_state(session_id)

        response_data = {"status": "success", "session_id": session_id, "is_blocked": is_blocked}

        if block_state:
            response_data.update(
                {
                    "reason": block_state.reason.value,
                    "message": block_state.message,
                    "alert_message": block_state.alert_message,
                    "detected_keywords": block_state.detected_keywords,
                    "blocked_at": block_state.blocked_at,
                }
            )

        await sio_instance.emit("block_status_response", response_data, room=sid)

    except Exception as e:
        log.error(f"Error handling block status request: {e}")
        await sio_instance.emit(
            "block_status_response", {"status": "error", "error": str(e)}, room=sid
        )


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


async def ai_chat_message(sid, data):
    """Handle AI chat messages with terminal context."""
    try:
        message = data.get("message", "")
        message_id = data.get("message_id", "")
        terminal_session = data.get("terminal_session")

        if not message:
            log.warning("Empty message received for AI chat")
            return

        log.info(f"Processing AI chat message from {sid}: {message[:100]}...")

        # Get AI service
        ai_service = get_ai_service()

        if not await ai_service.is_available():
            await sio_instance.emit(
                "ai_chat_error",
                {"message_id": message_id, "error": "AI service is not available"},
                room=sid,
            )
            return

        # Get terminal context if session is provided
        terminal_context = None
        if terminal_session:
            terminal_context = get_terminal_context(terminal_session)

        # Build messages array
        messages = [{"role": "user", "content": message}]

        # Stream AI response
        try:
            response_chunks = []
            async for chunk in ai_service.chat_completion(
                messages=messages, terminal_context=terminal_context, stream=True
            ):
                response_chunks.append(chunk)
                await sio_instance.emit(
                    "ai_chat_chunk", {"message_id": message_id, "chunk": chunk}, room=sid
                )

            # Send completion signal
            full_response = "".join(response_chunks)
            await sio_instance.emit(
                "ai_chat_complete",
                {"message_id": message_id, "full_response": full_response},
                room=sid,
            )

            log.info(f"AI chat completed for message_id: {message_id}")

        except Exception as e:
            log.error(f"Error during AI streaming: {e}")
            await sio_instance.emit(
                "ai_chat_error", {"message_id": message_id, "error": str(e)}, room=sid
            )

    except Exception as e:
        log.error(f"Error handling AI chat message: {e}")
        await sio_instance.emit(
            "ai_chat_error",
            {"message_id": data.get("message_id", ""), "error": "Internal server error"},
            room=sid,
        )


async def ai_terminal_analysis(sid, data):
    """Analyze terminal commands and provide AI suggestions."""
    try:
        command = data.get("command", "")
        terminal_session = data.get("terminal_session")
        analysis_id = data.get("analysis_id", "")

        if not command:
            log.warning("Empty command received for AI analysis")
            return

        log.info(f"Analyzing command for {sid}: {command}")

        # Get AI service
        ai_service = get_ai_service()

        if not await ai_service.is_available():
            await sio_instance.emit(
                "ai_analysis_error",
                {"analysis_id": analysis_id, "error": "AI service is not available"},
                room=sid,
            )
            return

        # Get terminal context
        terminal_context = get_terminal_context(terminal_session) if terminal_session else None

        # Build analysis prompt
        analysis_prompt = f"""Please analyze this terminal command and provide helpful information:

Command: {command}

Please provide:
1. What this command does
2. Any potential risks or considerations
3. Suggested improvements or alternatives if applicable
4. Expected output or behavior

Keep the response concise and practical."""

        messages = [{"role": "user", "content": analysis_prompt}]

        # Stream AI analysis
        try:
            response_chunks = []
            async for chunk in ai_service.chat_completion(
                messages=messages, terminal_context=terminal_context, stream=True
            ):
                response_chunks.append(chunk)
                await sio_instance.emit(
                    "ai_analysis_chunk", {"analysis_id": analysis_id, "chunk": chunk}, room=sid
                )

            # Send completion signal
            full_analysis = "".join(response_chunks)
            await sio_instance.emit(
                "ai_analysis_complete",
                {"analysis_id": analysis_id, "command": command, "analysis": full_analysis},
                room=sid,
            )

            log.info(f"AI command analysis completed for analysis_id: {analysis_id}")

        except Exception as e:
            log.error(f"Error during AI analysis: {e}")
            await sio_instance.emit(
                "ai_analysis_error", {"analysis_id": analysis_id, "error": str(e)}, room=sid
            )

    except Exception as e:
        log.error(f"Error handling AI terminal analysis: {e}")
        await sio_instance.emit(
            "ai_analysis_error",
            {"analysis_id": data.get("analysis_id", ""), "error": "Internal server error"},
            room=sid,
        )


async def ai_get_info(sid, data):
    """Get AI service information (model, provider, status)."""
    try:
        ai_service = get_ai_service()

        # Get AI service information
        provider = "unknown"
        model = "unknown"

        if hasattr(ai_service, "model"):
            model = ai_service.model
        if hasattr(ai_service, "__class__"):
            provider = ai_service.__class__.__name__.lower().replace("service", "")

        is_available = await ai_service.is_available()

        await sio_instance.emit(
            "ai_info_response",
            {
                "provider": provider,
                "model": model,
                "available": is_available,
                "status": "connected" if is_available else "disconnected",
            },
            room=sid,
        )

        log.info(
            f"AI info requested from {sid}: provider={provider}, model={model}, available={is_available}"
        )

    except Exception as e:
        log.error(f"Error getting AI info: {e}")
        await sio_instance.emit(
            "ai_info_response",
            {
                "provider": "error",
                "model": "error",
                "available": False,
                "status": "error",
                "error": str(e),
            },
            room=sid,
        )


# ============================================================
# Pane Management Handlers
# ============================================================


async def pane_create(sid, data):
    """新しいペーンを作成します。"""
    try:
        if not _pane_manager:
            await sio_instance.emit(
                "pane_error", {"error": "Pane manager not initialized"}, room=sid
            )
            return

        session_id = data.get("session_id", f"session_{uuid4().hex[:8]}")
        mode = data.get("mode", "terminal")  # 3-mode system: code-server, tmux, pilot-chat
        title = data.get("title", "")
        size = data.get("size", {"rows": 24, "cols": 80})

        config = PaneConfig(
            pane_type=PaneType.TERMINAL,
            title=title,
            size=size,
        )

        pane = await _pane_manager.create_agent_pane(
            parent_session_id=session_id, agent_type="default", config=config, mode=mode
        )

        _pane_manager.update_socket_mapping(pane.id, sid)

        await sio_instance.emit("pane_created", pane.to_dict(), room=sid)
        log.info(f"Pane created: {pane.id} in session {session_id} (Mode: {mode})")

    except Exception as e:
        log.error(f"Error creating pane: {e}", exc_info=True)
        await sio_instance.emit("pane_error", {"error": str(e)}, room=sid)


async def pane_destroy(sid, data):
    """Destroy a pane."""
    try:
        if not _pane_manager:
            await sio_instance.emit(
                "pane_error", {"error": "Pane manager not initialized"}, room=sid
            )
            return

        pane_id = data.get("pane_id")
        if not pane_id:
            await sio_instance.emit("pane_error", {"error": "pane_id required"}, room=sid)
            return

        success = await _pane_manager.destroy_pane(pane_id)

        if success:
            await sio_instance.emit("pane_destroyed", {"pane_id": pane_id}, room=sid)
            log.info(f"Pane destroyed: {pane_id}")
        else:
            await sio_instance.emit("pane_error", {"error": f"Pane {pane_id} not found"}, room=sid)

    except Exception as e:
        log.error(f"Error destroying pane: {e}")
        await sio_instance.emit("pane_error", {"error": str(e)}, room=sid)


async def pane_resize(sid, data):
    """Resize a pane terminal."""
    try:
        pane_id = data.get("pane_id")
        cols = data.get("cols", 80)
        rows = data.get("rows", 24)

        if not _pane_manager:
            return

        pane = _pane_manager.get_pane(pane_id)
        if pane and pane.terminal_id and pane.terminal_id in AsyncioTerminal.sessions:
            terminal = AsyncioTerminal.sessions[pane.terminal_id]
            await terminal.resize(cols, rows)

    except Exception as e:
        log.error(f"Error resizing pane: {e}")


async def pane_focus(sid, data):
    """Focus a pane."""
    try:
        pane_id = data.get("pane_id")
        if not _pane_manager:
            return

        pane = _pane_manager.get_pane(pane_id)
        if pane:
            await sio_instance.emit("pane_focused", {"pane_id": pane_id}, room=sid)
            log.debug(f"Pane focused: {pane_id}")

    except Exception as e:
        log.error(f"Error focusing pane: {e}")


async def pane_list(sid, data):
    """ペーン一覧を取得します。"""
    try:
        if not _pane_manager:
            await sio_instance.emit("pane_list_response", {"panes": []}, room=sid)
            return

        session_id = data.get("session_id")
        panes = _pane_manager.list_panes(parent_session_id=session_id)

        await sio_instance.emit(
            "pane_list_response", {"panes": [p.to_dict() for p in panes]}, room=sid
        )

    except Exception as e:
        log.error(f"Error listing panes: {e}")
        await sio_instance.emit("pane_list_response", {"panes": [], "error": str(e)}, room=sid)


async def session_list(sid, data):
    """セッション一覧を取得します。"""
    try:
        if not _pane_manager:
            await sio_instance.emit("session_list_response", {"sessions": []}, room=sid)
            return

        sessions = _pane_manager.list_sessions()
        await sio_instance.emit(
            "session_list_response", {"sessions": [s.to_dict() for s in sessions]}, room=sid
        )

    except Exception as e:
        log.error(f"Error listing sessions: {e}")
        await sio_instance.emit(
            "session_list_response", {"sessions": [], "error": str(e)}, room=sid
        )


# ============================================================
# AI Command Execution Handlers
# ============================================================

# Execution mode per socket: "approval" (default) or "auto"
_execution_modes: dict = {}


async def ai_execute_command(sid, data):
    """Execute a command proposed by AI in a target pane/terminal."""
    try:
        pane_id = data.get("pane_id")
        command = data.get("command", "")
        command_id = data.get("command_id", "")

        if not command:
            await sio_instance.emit(
                "command_blocked",
                {
                    "command_id": command_id,
                    "reason": "Empty command",
                },
                room=sid,
            )
            return

        # Check with AutoBlocker
        auto_blocker = get_auto_blocker()

        # Determine the target session
        target_session_id = None
        if pane_id and _pane_manager:
            pane = _pane_manager.get_pane(pane_id)
            if pane and pane.terminal_id:
                target_session_id = pane.terminal_id
        else:
            # Fallback: use first available session
            for session_id, terminal in AsyncioTerminal.sessions.items():
                if not terminal.closed:
                    target_session_id = session_id
                    break

        if not target_session_id or target_session_id not in AsyncioTerminal.sessions:
            await sio_instance.emit(
                "command_blocked",
                {
                    "command_id": command_id,
                    "reason": "No active terminal session",
                },
                room=sid,
            )
            return

        # Check if command is blocked
        if auto_blocker.is_session_blocked(target_session_id):
            await sio_instance.emit(
                "command_blocked",
                {
                    "command_id": command_id,
                    "reason": "Session is currently blocked",
                },
                room=sid,
            )
            return

        # Write command to terminal (append newline to execute)
        terminal = AsyncioTerminal.sessions[target_session_id]
        await terminal.write(command + "\n")

        await sio_instance.emit(
            "command_executed",
            {
                "command_id": command_id,
                "pane_id": pane_id,
            },
            room=sid,
        )

        log.info(f"AI command executed: '{command}' in session {target_session_id}")

    except Exception as e:
        log.error(f"Error executing AI command: {e}")
        await sio_instance.emit(
            "command_blocked",
            {
                "command_id": data.get("command_id", ""),
                "reason": str(e),
            },
            room=sid,
        )


async def ai_set_execution_mode(sid, data):
    """Set AI command execution mode (approval or auto)."""
    try:
        mode = data.get("mode", "approval")
        if mode not in ("approval", "auto"):
            mode = "approval"

        _execution_modes[sid] = mode

        await sio_instance.emit(
            "execution_mode_changed",
            {
                "mode": mode,
            },
            room=sid,
        )

        log.info(f"Execution mode set to '{mode}' for client {sid}")

    except Exception as e:
        log.error(f"Error setting execution mode: {e}")


async def pane_input(sid, data):
    """Handle input to a specific pane's terminal."""
    try:
        pane_id = data.get("pane_id")
        input_data = data.get("data", "")

        if not _pane_manager:
            return

        pane = _pane_manager.get_pane(pane_id)
        if pane and pane.terminal_id and pane.terminal_id in AsyncioTerminal.sessions:
            terminal = AsyncioTerminal.sessions[pane.terminal_id]
            await terminal.write(input_data)
        else:
            log.warning(f"Pane {pane_id} terminal not found")

    except Exception as e:
        log.error(f"Error handling pane input: {e}")


# ============================================================
# ZMQ Command Handlers (AgentShell Observer Pattern)
# ============================================================


async def handle_zmq_command_inject(message):
    """Handle COMMAND_INJECT from ZMQ (AgentShell → PTY).

    Writes the command directly to the target terminal's PTY.
    """
    try:
        session_id = message.payload.get("session_id")
        command = message.payload.get("command", "")

        if not session_id or not command:
            log.warning("COMMAND_INJECT missing session_id or command")
            return

        if session_id not in AsyncioTerminal.sessions:
            log.warning(f"COMMAND_INJECT: session {session_id} not found")
            return

        terminal = AsyncioTerminal.sessions[session_id]
        if terminal.closed:
            log.warning(f"COMMAND_INJECT: session {session_id} is closed")
            return

        await terminal.write(command + "\n")
        log.info(f"COMMAND_INJECT executed in session {session_id}: {command[:80]}")

        # Notify frontend that a command was injected
        if sio_instance:
            await sio_instance.emit(
                "agent_command_injected",
                {
                    "session_id": session_id,
                    "command": command,
                    "agent_id": message.from_agent,
                },
            )

    except Exception as e:
        log.error(f"Error handling COMMAND_INJECT: {e}")


async def handle_zmq_command_propose(message):
    """Handle COMMAND_PROPOSE from ZMQ (AgentShell → Frontend).

    Forwards the command proposal to the frontend via Socket.IO
    for user approval ([Run]/[Skip]).
    """
    try:
        session_id = message.payload.get("session_id", "")
        command = message.payload.get("command", "")
        description = message.payload.get("description", "")

        if not command:
            log.warning("COMMAND_PROPOSE missing command")
            return

        if sio_instance:
            await sio_instance.emit(
                "command_proposed",
                {
                    "session_id": session_id,
                    "from_agent": message.from_agent,
                    "command": command,
                    "description": description,
                    "require_approval": message.payload.get("require_approval", True),
                    "message_id": str(message.message_id),
                },
            )
            log.info(
                f"COMMAND_PROPOSE forwarded to frontend: {command[:80]} (from {message.from_agent})"
            )

    except Exception as e:
        log.error(f"Error handling COMMAND_PROPOSE: {e}")

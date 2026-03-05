"""
AI-related Socket.IO event handlers.
"""

import logging

from aetherterm.agentserver.ai_services import get_ai_service

from .helpers import get_sio, get_terminal_context

log = logging.getLogger("aetherterm.socket_handlers")


async def ai_chat_message(sid, data):
    """Handle AI chat messages with terminal context."""
    sio = get_sio()
    try:
        message = data.get("message", "")
        message_id = data.get("message_id", "")
        terminal_session = data.get("terminal_session")

        if not message:
            log.warning("Empty message received for AI chat")
            return

        log.info(f"Processing AI chat message from {sid}: {message[:100]}...")

        ai_service = get_ai_service()

        if not await ai_service.is_available():
            await sio.emit(
                "ai_chat_error",
                {"message_id": message_id, "error": "AI service is not available"},
                room=sid,
            )
            return

        terminal_context = get_terminal_context(terminal_session) if terminal_session else None

        messages = [{"role": "user", "content": message}]

        try:
            response_chunks = []
            async for chunk in ai_service.chat_completion(
                messages=messages, terminal_context=terminal_context, stream=True
            ):
                response_chunks.append(chunk)
                await sio.emit(
                    "ai_chat_chunk", {"message_id": message_id, "chunk": chunk}, room=sid
                )

            full_response = "".join(response_chunks)
            await sio.emit(
                "ai_chat_complete",
                {"message_id": message_id, "full_response": full_response},
                room=sid,
            )

            log.info(f"AI chat completed for message_id: {message_id}")

        except Exception as e:
            log.error(f"Error during AI streaming: {e}")
            await sio.emit(
                "ai_chat_error", {"message_id": message_id, "error": str(e)}, room=sid
            )

    except Exception as e:
        log.error(f"Error handling AI chat message: {e}")
        await sio.emit(
            "ai_chat_error",
            {"message_id": data.get("message_id", ""), "error": "Internal server error"},
            room=sid,
        )


async def ai_terminal_analysis(sid, data):
    """Analyze terminal commands and provide AI suggestions."""
    sio = get_sio()
    try:
        command = data.get("command", "")
        terminal_session = data.get("terminal_session")
        analysis_id = data.get("analysis_id", "")

        if not command:
            log.warning("Empty command received for AI analysis")
            return

        log.info(f"Analyzing command for {sid}: {command}")

        ai_service = get_ai_service()

        if not await ai_service.is_available():
            await sio.emit(
                "ai_analysis_error",
                {"analysis_id": analysis_id, "error": "AI service is not available"},
                room=sid,
            )
            return

        terminal_context = get_terminal_context(terminal_session) if terminal_session else None

        analysis_prompt = f"""Please analyze this terminal command and provide helpful information:

Command: {command}

Please provide:
1. What this command does
2. Any potential risks or considerations
3. Suggested improvements or alternatives if applicable
4. Expected output or behavior

Keep the response concise and practical."""

        messages = [{"role": "user", "content": analysis_prompt}]

        try:
            response_chunks = []
            async for chunk in ai_service.chat_completion(
                messages=messages, terminal_context=terminal_context, stream=True
            ):
                response_chunks.append(chunk)
                await sio.emit(
                    "ai_analysis_chunk", {"analysis_id": analysis_id, "chunk": chunk}, room=sid
                )

            full_analysis = "".join(response_chunks)
            await sio.emit(
                "ai_analysis_complete",
                {"analysis_id": analysis_id, "command": command, "analysis": full_analysis},
                room=sid,
            )

            log.info(f"AI command analysis completed for analysis_id: {analysis_id}")

        except Exception as e:
            log.error(f"Error during AI analysis: {e}")
            await sio.emit(
                "ai_analysis_error", {"analysis_id": analysis_id, "error": str(e)}, room=sid
            )

    except Exception as e:
        log.error(f"Error handling AI terminal analysis: {e}")
        await sio.emit(
            "ai_analysis_error",
            {"analysis_id": data.get("analysis_id", ""), "error": "Internal server error"},
            room=sid,
        )


async def ai_get_info(sid, data):
    """Get AI service information (model, provider, status)."""
    sio = get_sio()
    try:
        ai_service = get_ai_service()

        provider = "unknown"
        model = "unknown"

        if hasattr(ai_service, "model"):
            model = ai_service.model
        if hasattr(ai_service, "__class__"):
            provider = ai_service.__class__.__name__.lower().replace("service", "")

        is_available = await ai_service.is_available()

        await sio.emit(
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
        await sio.emit(
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

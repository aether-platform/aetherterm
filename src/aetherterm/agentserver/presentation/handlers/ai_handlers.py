"""
AI Chat & Log Search WebSocket Handlers - Interface Layer

Simplified AI handlers for chat and log search functionality only.
"""

import logging
from datetime import datetime

from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal
from aetherterm.agentserver.infrastructure.config.di_container import get_container

# from dependency_injector.wiring import inject, Provide

log = logging.getLogger("aetherterm.handlers.ai")


async def ai_chat_message(sid, data):
    """Handle AI chat message requests."""
    print(f"DEBUG: ai_chat_message called from sid: {sid}, data: {data}")
    log.info(f"ai_chat_message called from sid: {sid}, data: {data}")
    from aetherterm.agentserver.presentation.websocket.socket_handlers import sio_instance

    container = get_container()
    ai_service = container.infrastructure.ai_service()
    print(f"DEBUG: AI service provider: {ai_service.provider}")
    try:
        message = data.get("message", "")
        session_id = data.get("session_id")
        message_id = data.get("message_id")
        stream = data.get("stream", False)

        if not message:
            await sio_instance.emit("error", {"message": "Message required"}, room=sid)
            return

        # Prepare context from terminal session if available
        terminal_context = {}
        if session_id and session_id in AsyncioTerminal.sessions:
            terminal = AsyncioTerminal.sessions[session_id]
            terminal_context = {
                "recent_history": terminal.history[-1000:] if terminal.history else "",
                "session_id": session_id,
                "working_directory": getattr(terminal, "current_dir", "/"),
            }

        # Prepare messages for AI service
        messages = [{"role": "user", "content": message}]

        # Use AI service for chat processing
        response_generator = ai_service.chat_completion(
            messages=messages, terminal_context=terminal_context, stream=stream
        )

        if stream:
            # Send streaming response
            full_response = ""
            async for chunk in response_generator:
                full_response += chunk
                await sio_instance.emit(
                    "ai_chat_chunk",
                    {
                        "chunk": chunk,
                        "message_id": message_id,
                        "session_id": session_id,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                    room=sid,
                )

            # Send final complete response
            await sio_instance.emit(
                "ai_chat_complete",
                {
                    "full_response": full_response,
                    "message_id": message_id,
                    "session_id": session_id,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                room=sid,
            )
        else:
            # Send complete response
            response = ""
            async for chunk in response_generator:
                response += chunk

            await sio_instance.emit(
                "ai_chat_response",
                {
                    "response": response,
                    "session_id": session_id,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                room=sid,
            )

    except Exception as e:
        log.error(f"Failed to process AI chat message: {e}")
        await sio_instance.emit(
            "ai_chat_error",
            {
                "error": str(e),
                "message_id": data.get("message_id"),
                "session_id": data.get("session_id"),
            },
            room=sid,
        )


async def ai_log_search(sid, data):
    """Search logs using AI-enhanced matching."""
    from aetherterm.agentserver.presentation.websocket.socket_handlers import sio_instance

    container = get_container()
    ai_service = container.infrastructure.ai_service()
    try:
        query = data.get("query", "")
        session_id = data.get("session_id")
        limit = data.get("limit", 50)

        if not query:
            await sio_instance.emit("error", {"message": "Search query required"}, room=sid)
            return

        # Get logs from AsyncioTerminal
        recent_logs = AsyncioTerminal.get_recent_logs(limit=1000)

        # Filter by session if specified
        if session_id:
            recent_logs = [log for log in recent_logs if log.get("session_id") == session_id]

        # Use AI service for enhanced search
        search_results = await ai_service.search_logs(query=query, logs=recent_logs, limit=limit)

        await sio_instance.emit(
            "ai_log_search_results",
            {
                "query": query,
                "results": search_results,
                "total_found": len(search_results),
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat(),
            },
            room=sid,
        )

    except Exception as e:
        log.error(f"Failed to search logs: {e}")
        await sio_instance.emit("error", {"message": str(e)}, room=sid)


async def ai_search_suggestions(sid, data):
    """Get search term suggestions for log search."""
    from aetherterm.agentserver.presentation.websocket.socket_handlers import sio_instance

    container = get_container()
    ai_service = container.infrastructure.ai_service()
    try:
        partial_query = data.get("partial_query", "")

        # Use AI service for search suggestions
        suggestions = await ai_service.suggest_search_terms(partial_query)

        await sio_instance.emit(
            "ai_search_suggestions",
            {
                "partial_query": partial_query,
                "suggestions": suggestions,
                "timestamp": datetime.utcnow().isoformat(),
            },
            room=sid,
        )

    except Exception as e:
        log.error(f"Failed to get search suggestions: {e}")
        await sio_instance.emit("error", {"message": str(e)}, room=sid)


async def ai_get_info(sid, data):
    """Get AI service information and status."""
    print(f"DEBUG: ai_get_info called from sid: {sid}")
    log.info(f"ai_get_info called from sid: {sid}")

    # Get sio_instance from global or container
    from aetherterm.agentserver.presentation.websocket.socket_handlers import sio_instance

    container = get_container()
    ai_service = container.infrastructure.ai_service()
    print(f"DEBUG: AI service provider: {ai_service.provider}")
    try:
        # Get AI service info
        provider_name = ai_service.provider_name
        model_info = ai_service.get_model_info()
        is_connected = await ai_service.check_connection()
        retry_status = ai_service.get_retry_status()

        response_data = {
            "provider": provider_name,
            "model": model_info.get("model", "unknown"),
            "available": is_connected,  # Frontend expects 'available' not 'is_connected'
            "status": "connected" if is_connected else "disconnected",
            "capabilities": {"chat": True, "log_search": True, "streaming": True},
            "retry_status": retry_status,  # Include retry status
            "timestamp": datetime.utcnow().isoformat(),
        }

        log.info(f"Sending ai_info_response: {response_data}")
        await sio_instance.emit("ai_info_response", response_data, room=sid)

    except Exception as e:
        log.error(f"Failed to get AI info: {e}")
        await sio_instance.emit("error", {"message": str(e)}, room=sid)


async def ai_reset_retry(sid, data):
    """Reset AI service retry state."""
    log.info(f"ai_reset_retry called from sid: {sid}")

    from aetherterm.agentserver.presentation.websocket.socket_handlers import sio_instance

    container = get_container()
    ai_service = container.infrastructure.ai_service()

    try:
        # Reset retry state
        ai_service.reset_retry_state()

        # Get updated status
        retry_status = ai_service.get_retry_status()
        is_connected = await ai_service.check_connection()

        response_data = {
            "success": True,
            "message": "AI service retry state has been reset",
            "retry_status": retry_status,
            "available": is_connected,
            "timestamp": datetime.utcnow().isoformat(),
        }

        log.info(f"Sending ai_reset_retry_response: {response_data}")
        await sio_instance.emit("ai_reset_retry_response", response_data, room=sid)

        # Also send updated info
        await ai_get_info(sid, {})

    except Exception as e:
        log.error(f"Failed to reset AI retry state: {e}")
        await sio_instance.emit("error", {"message": str(e)}, room=sid)


# All other AI functions removed - focusing only on chat and log search
# Use local insights API for analytics and suggestions

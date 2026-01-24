"""Log monitoring and control handlers."""

import asyncio
import logging
from .base import sio_instance, socket_error_handler, log_processing_manager

log = logging.getLogger("aetherterm.socket_handlers")

# Event-driven log statistics broadcasting
_log_stats_task = None
_log_stats_interval = 5  # seconds


@socket_error_handler("log_monitor_error")
async def log_monitor_subscribe(sid, data):
    """Subscribe to log monitoring updates."""
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


@socket_error_handler("log_monitor_error")
async def log_monitor_unsubscribe(sid, data):
    """Unsubscribe from log monitoring updates."""
    terminal_id = data.get("terminal_id")
    log.info(f"Client {sid} unsubscribing from log monitor for terminal {terminal_id}")

    # Leave log monitoring room
    await sio_instance.leave_room(sid, f"log_monitor_{terminal_id}")

    await sio_instance.emit(
        "log_monitor_unsubscribed", {"status": "success", "terminal_id": terminal_id}, room=sid
    )


@socket_error_handler("log_search_error")
async def log_monitor_search(sid, data):
    """Handle log search requests."""
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
    """Schedule the next log statistics broadcast."""
    await asyncio.sleep(_log_stats_interval)
    await broadcast_log_statistics()


def start_log_monitoring_background_task():
    """Start the background task for log monitoring."""
    global _log_stats_task
    if _log_stats_task is None or _log_stats_task.done():
        _log_stats_task = asyncio.create_task(broadcast_log_statistics())
        log.info("Started log monitoring background task")


def stop_log_monitoring_background_task():
    """Stop the background task for log monitoring."""
    global _log_stats_task
    if _log_stats_task and not _log_stats_task.done():
        _log_stats_task.cancel()
        log.info("Stopped log monitoring background task")


async def start_redis_pubsub_listener():
    """Start Redis pub/sub listener for real-time log events."""
    try:
        import redis.asyncio as redis
        
        redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        pubsub = redis_client.pubsub()
        
        # Subscribe to terminal log channels
        await pubsub.subscribe("terminal_logs:*")
        
        log.info("Started Redis pub/sub listener for log events")
        
        async for message in pubsub.listen():
            if message["type"] == "message":
                await handle_realtime_log_event(message["channel"], message["data"])
                
    except Exception as e:
        log.error(f"Error in Redis pub/sub listener: {e}")


async def handle_realtime_log_event(channel: str, message: str):
    """Handle real-time log events from Redis pub/sub."""
    try:
        import json
        
        # Parse channel to get terminal ID
        if channel.startswith("terminal_logs:"):
            terminal_id = channel.split(":", 1)[1]
            
            # Parse log event
            try:
                log_event = json.loads(message)
            except json.JSONDecodeError:
                log_event = {"content": message, "timestamp": asyncio.get_event_loop().time()}
            
            # Broadcast to log monitor subscribers
            room_name = f"log_monitor_{terminal_id}"
            await sio_instance.emit(
                "realtime_log_event",
                {
                    "terminal_id": terminal_id,
                    "event": log_event,
                },
                room=room_name,
            )
            
            # Update statistics
            await update_and_broadcast_statistics()
            
    except Exception as e:
        log.error(f"Error handling realtime log event: {e}")


async def update_and_broadcast_statistics():
    """Update and broadcast log statistics."""
    try:
        if log_processing_manager:
            # Get updated statistics
            stats = await log_processing_manager.get_system_statistics()
            
            # Broadcast to all log monitor subscribers
            await sio_instance.emit(
                "log_system_stats_update",
                {"stats": stats, "timestamp": asyncio.get_event_loop().time()},
                namespace="/",
            )
            
    except Exception as e:
        log.error(f"Error updating log statistics: {e}")


@socket_error_handler("control_error")
async def control_message(sid, data):
    """Handle control messages for log processing."""
    command = data.get("command")
    
    if command == "start_processing":
        if log_processing_manager:
            await log_processing_manager.start_processing()
            await sio_instance.emit(
                "control_response",
                {"command": command, "status": "started"},
                room=sid,
            )
        else:
            await sio_instance.emit(
                "control_error",
                {"error": "Log processing manager not available"},
                room=sid,
            )
            
    elif command == "stop_processing":
        if log_processing_manager:
            await log_processing_manager.stop_processing()
            await sio_instance.emit(
                "control_response",
                {"command": command, "status": "stopped"},
                room=sid,
            )
        else:
            await sio_instance.emit(
                "control_error",
                {"error": "Log processing manager not available"},
                room=sid,
            )
            
    elif command == "get_status":
        if log_processing_manager:
            status = await log_processing_manager.get_processing_status()
            await sio_instance.emit(
                "control_response",
                {"command": command, "status": status},
                room=sid,
            )
        else:
            await sio_instance.emit(
                "control_response",
                {"command": command, "status": "unavailable"},
                room=sid,
            )
            
    else:
        await sio_instance.emit(
            "control_error",
            {"error": f"Unknown command: {command}"},
            room=sid,
        )


@socket_error_handler("wrapper_error")
async def wrapper_session_sync(sid, data):
    """Handle wrapper session synchronization."""
    session_id = data.get("session_id")
    wrapper_data = data.get("wrapper_data", {})
    
    log.info(f"Syncing wrapper session {session_id} from client {sid}")
    
    # Store wrapper session data
    # Implementation would depend on your session storage system
    
    await sio_instance.emit(
        "wrapper_session_synced",
        {
            "session_id": session_id,
            "status": "synced",
        },
        room=sid,
    )


@socket_error_handler("wrapper_error")
async def get_wrapper_sessions(sid, data):
    """Get all wrapper sessions."""
    # Implementation would depend on your session storage system
    sessions = []  # Placeholder
    
    await sio_instance.emit(
        "wrapper_sessions",
        {
            "sessions": sessions,
            "count": len(sessions),
        },
        room=sid,
    )
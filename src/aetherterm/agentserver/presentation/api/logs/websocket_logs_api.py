"""
WebSocket Logs API - Real-time Log Streaming

Provides WebSocket endpoints for real-time log streaming and monitoring.
"""

import json
import logging
from typing import Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal

log = logging.getLogger("aetherterm.api.logs.websocket")

# Initialize router
router = APIRouter()


@router.websocket("/stream")
async def websocket_log_stream(websocket: WebSocket):
    """WebSocket endpoint for real-time log streaming."""
    await websocket.accept()
    client_id = id(websocket)

    try:
        # Register client for log updates
        AsyncioTerminal.log_subscribers.add(client_id)

        await websocket.send_text(
            json.dumps(
                {
                    "type": "connection_established",
                    "client_id": client_id,
                    "message": "Connected to log stream",
                }
            )
        )

        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for client messages (ping, filter updates, etc.)
                data = await websocket.receive_text()
                message = json.loads(data)

                if message.get("type") == "ping":
                    await websocket.send_text(
                        json.dumps({"type": "pong", "timestamp": message.get("timestamp")})
                    )
                elif message.get("type") == "filter_update":
                    # Handle filter updates for this client
                    # This would be stored per-client if implemented
                    await websocket.send_text(
                        json.dumps(
                            {"type": "filter_updated", "filters": message.get("filters", {})}
                        )
                    )

            except WebSocketDisconnect:
                break
            except Exception as e:
                log.error(f"Error handling WebSocket message: {e}")
                break

    except WebSocketDisconnect:
        log.info(f"WebSocket client {client_id} disconnected")
    except Exception as e:
        log.error(f"WebSocket error for client {client_id}: {e}")
    finally:
        # Clean up: remove client from subscribers
        AsyncioTerminal.log_subscribers.discard(client_id)


async def broadcast_log_to_websockets(log_entry: Dict):
    """Broadcast log entry to all connected WebSocket clients."""
    if not AsyncioTerminal.log_subscribers:
        return

    message = json.dumps({"type": "log_entry", "data": log_entry})

    # In a real implementation, you would iterate through actual WebSocket connections
    # For now, this is a placeholder for the broadcasting mechanism
    log.debug(f"Broadcasting log entry to {len(AsyncioTerminal.log_subscribers)} subscribers")

"""
Socket.IO ブロードキャスター実装

BroadcasterPort の Socket.IO アダプター。
"""

import logging
from typing import Any, Dict, Sequence

from ...application.ports.broadcaster import BroadcasterPort

logger = logging.getLogger(__name__)


class SocketIOBroadcaster(BroadcasterPort):
    """Socket.IO を使用したブロードキャスター"""

    def __init__(self, sio):
        self._sio = sio

    async def emit_to_client(self, event: str, data: Dict[str, Any], client_id: str) -> None:
        await self._sio.emit(event, data, room=client_id)

    async def emit_to_clients(
        self, event: str, data: Dict[str, Any], client_ids: Sequence[str]
    ) -> None:
        for client_id in client_ids:
            await self._sio.emit(event, data, room=client_id)

    async def broadcast(self, event: str, data: Dict[str, Any]) -> None:
        await self._sio.emit(event, data)

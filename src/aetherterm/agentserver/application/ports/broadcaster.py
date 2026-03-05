"""
ブロードキャスターポート

クライアントへのメッセージ送信を抽象化します。
Socket.IO等の具体的なトランスポートに依存しません。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Sequence


class BroadcasterPort(ABC):
    """クライアントへのメッセージ送信ポート"""

    @abstractmethod
    async def emit_to_client(self, event: str, data: Dict[str, Any], client_id: str) -> None:
        """特定のクライアントにイベントを送信"""

    @abstractmethod
    async def emit_to_clients(
        self, event: str, data: Dict[str, Any], client_ids: Sequence[str]
    ) -> None:
        """複数のクライアントにイベントを送信"""

    @abstractmethod
    async def broadcast(self, event: str, data: Dict[str, Any]) -> None:
        """全クライアントにブロードキャスト"""

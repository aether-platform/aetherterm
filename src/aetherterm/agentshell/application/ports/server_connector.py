"""
サーバーコネクターポート

AgentServerとの通信を抽象化するインターフェースを定義します。
WebSocket等の具体的なプロトコルに依存しません。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class ServerConnectorPort(ABC):
    """サーバーコネクターポート"""

    @abstractmethod
    async def send_event(self, event: str, data: Dict[str, Any]) -> None:
        """サーバーにイベントを送信"""

    @abstractmethod
    async def sync_session(self, session_data: Dict[str, Any]) -> None:
        """セッション情報をサーバーと同期"""

    @abstractmethod
    async def is_connected(self) -> bool:
        """サーバーとの接続状態を確認"""

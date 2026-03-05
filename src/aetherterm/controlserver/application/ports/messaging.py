"""
メッセージングポート

メッセージブローカーとの通信を抽象化するインターフェースを定義します。
NATS等の具体的なメッセージングシステムに依存しません。
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict


class MessagingPort(ABC):
    """メッセージングポート"""

    @abstractmethod
    async def publish(self, subject: str, data: Dict[str, Any]) -> None:
        """メッセージをパブリッシュ"""

    @abstractmethod
    async def subscribe(self, subject: str, handler: Callable) -> None:
        """サブジェクトをサブスクライブ"""

    @abstractmethod
    async def connect(self) -> None:
        """ブローカーに接続"""

    @abstractmethod
    async def close(self) -> None:
        """接続を閉じる"""

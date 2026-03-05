"""
ターミナルI/Oポート

ターミナルへの読み書きを抽象化するインターフェースを定義します。
PTY操作等の具体的な実装に依存しません。
"""

from abc import ABC, abstractmethod
from typing import Optional


class TerminalIOPort(ABC):
    """ターミナルI/Oポート"""

    @abstractmethod
    async def write_output(self, data: str) -> None:
        """ターミナルに出力を書き込み"""

    @abstractmethod
    async def read_input(self) -> Optional[str]:
        """ターミナルからの入力を読み取り"""

    @abstractmethod
    async def send_warning(self, message: str) -> None:
        """ターミナルに警告メッセージを表示"""

    @abstractmethod
    async def send_error(self, message: str) -> None:
        """ターミナルにエラーメッセージを表示"""

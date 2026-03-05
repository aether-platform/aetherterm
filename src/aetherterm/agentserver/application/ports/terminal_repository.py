"""
ターミナルリポジトリポート

ターミナルセッションの保存・取得を抽象化します。
クラスレベルのdict等、具体的なストレージに依存しません。
"""

from abc import ABC, abstractmethod
from typing import Any, List, Optional, Set

from ...domain.entities import SessionOwner, TerminalSessionInfo


class TerminalRepositoryPort(ABC):
    """ターミナルセッションリポジトリポート"""

    @abstractmethod
    def get_session(self, session_id: str) -> Optional[Any]:
        """セッションのターミナルインスタンスを取得"""

    @abstractmethod
    def session_exists(self, session_id: str) -> bool:
        """セッションが存在するか確認"""

    @abstractmethod
    def is_session_closed(self, session_id: str) -> bool:
        """セッションが閉じられたか確認"""

    @abstractmethod
    def get_session_info(self, session_id: str) -> Optional[TerminalSessionInfo]:
        """セッション情報を取得"""

    @abstractmethod
    def get_session_owner(self, session_id: str) -> Optional[SessionOwner]:
        """セッションの所有者情報を取得"""

    @abstractmethod
    def get_client_sids(self, session_id: str) -> Set[str]:
        """セッションに接続されているクライアントSIDを取得"""

    @abstractmethod
    def get_terminal_context(self, session_id: str) -> Optional[str]:
        """AI支援用のターミナルコンテキストを取得"""

    @abstractmethod
    def add_client_to_session(self, session_id: str, client_sid: str) -> bool:
        """セッションにクライアントを追加。成功時True"""

    @abstractmethod
    def remove_client_from_session(self, session_id: str, client_sid: str) -> int:
        """セッションからクライアントを削除。残りクライアント数を返す"""

    @abstractmethod
    def get_all_sessions_for_client(self, client_sid: str) -> List[str]:
        """クライアントが接続しているすべてのセッションIDを返す"""

    @abstractmethod
    async def write_to_session(self, session_id: str, data: str) -> bool:
        """セッションのターミナルにデータを書き込み"""

    @abstractmethod
    async def resize_session(self, session_id: str, cols: int, rows: int) -> bool:
        """セッションのターミナルをリサイズ"""

    @abstractmethod
    async def close_session(self, session_id: str) -> None:
        """セッションを閉じる"""

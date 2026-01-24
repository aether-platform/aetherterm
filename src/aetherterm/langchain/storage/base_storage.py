"""
ストレージアダプター基底クラス
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from ..models.conversation import ConversationEntry
from ..models.session import SessionContext, SessionSummary

logger = logging.getLogger(__name__)
class MemoryStorageAdapter(ABC):
    """メモリストレージアダプターの抽象基底クラス"""

    @abstractmethod
    async def store_conversation(self, entry: ConversationEntry) -> str:
        """
        会話エントリを保存

        Args:
            entry: 会話エントリ

        Returns:
            str: 保存されたエントリのID
        """

    @abstractmethod
    async def retrieve_conversations(
        self, session_id: str, limit: int = 10, offset: int = 0
    ) -> List[ConversationEntry]:
        """
        会話履歴を取得

        Args:
            session_id: セッションID
            limit: 取得件数制限
            offset: オフセット

        Returns:
            List[ConversationEntry]: 会話履歴
        """

    @abstractmethod
    async def search_conversations(
        self, query: str, session_id: Optional[str] = None, limit: int = 10, threshold: float = 0.7
    ) -> List[ConversationEntry]:
        """
        会話を検索

        Args:
            query: 検索クエリ
            session_id: セッションID（指定時はセッション内検索）
            limit: 取得件数制限
            threshold: 類似度閾値

        Returns:
            List[ConversationEntry]: 検索結果
        """

    @abstractmethod
    async def delete_old_conversations(self, days: int) -> int:
        """
        古い会話を削除

        Args:
            days: 保持日数

        Returns:
            int: 削除された件数
        """

    @abstractmethod
    async def get_conversation_statistics(self, session_id: str) -> Dict[str, Any]:
        """
        会話統計情報を取得

        Args:
            session_id: セッションID

        Returns:
            Dict[str, Any]: 統計情報
        """
class SessionStorageAdapter(ABC):
    """セッションストレージアダプターの抽象基底クラス"""

    @abstractmethod
    async def store_session_context(self, context: SessionContext) -> None:
        """
        セッションコンテキストを保存

        Args:
            context: セッションコンテキスト
        """

    @abstractmethod
    async def retrieve_session_context(self, session_id: str) -> Optional[SessionContext]:
        """
        セッションコンテキストを取得

        Args:
            session_id: セッションID

        Returns:
            Optional[SessionContext]: セッションコンテキスト
        """

    @abstractmethod
    async def update_session_activity(self, session_id: str) -> None:
        """
        セッションアクティビティを更新

        Args:
            session_id: セッションID
        """

    @abstractmethod
    async def list_active_sessions(self) -> List[SessionContext]:
        """
        アクティブセッション一覧を取得

        Returns:
            List[SessionContext]: アクティブセッション一覧
        """

    @abstractmethod
    async def cleanup_expired_sessions(self, timeout_minutes: int = 60) -> int:
        """
        期限切れセッションをクリーンアップ

        Args:
            timeout_minutes: タイムアウト時間（分）

        Returns:
            int: クリーンアップされたセッション数
        """
class SummaryStorageAdapter(ABC):
    """要約ストレージアダプターの抽象基底クラス"""

    @abstractmethod
    async def store_summary(self, summary: SessionSummary) -> str:
        """
        要約を保存

        Args:
            summary: セッション要約

        Returns:
            str: 保存された要約のID
        """

    @abstractmethod
    async def retrieve_summaries(
        self, session_id: str, summary_type: Optional[str] = None
    ) -> List[SessionSummary]:
        """
        要約を取得

        Args:
            session_id: セッションID
            summary_type: 要約タイプ

        Returns:
            List[SessionSummary]: 要約一覧
        """

    @abstractmethod
    async def search_summaries(self, query: str, limit: int = 10) -> List[SessionSummary]:
        """
        要約を検索

        Args:
            query: 検索クエリ
            limit: 取得件数制限

        Returns:
            List[SessionSummary]: 検索結果
        """

    @abstractmethod
    async def delete_old_summaries(self, days: int) -> int:
        """
        古い要約を削除

        Args:
            days: 保持日数

        Returns:
            int: 削除された件数
        """
class VectorStorageAdapter(ABC):
    """ベクトルストレージアダプターの抽象基底クラス"""

    @abstractmethod
    async def generate_embedding(self, text: str) -> List[float]:
        """
        テキストの埋め込みベクトルを生成

        Args:
            text: テキスト

        Returns:
            List[float]: 埋め込みベクトル
        """

    @abstractmethod
    async def store_embedding(
        self, content_id: str, content: str, embedding: List[float], metadata: Dict[str, Any] = None
    ) -> str:
        """
        埋め込みベクトルを保存

        Args:
            content_id: コンテンツID
            content: コンテンツ
            embedding: 埋め込みベクトル
            metadata: メタデータ

        Returns:
            str: 保存されたエントリのID
        """

    @abstractmethod
    async def similarity_search(
        self, query: str, limit: int = 10, threshold: float = 0.7, filters: Dict[str, Any] = None
    ) -> List[Tuple[str, float]]:
        """
        類似性検索

        Args:
            query: 検索クエリ
            limit: 取得件数制限
            threshold: 類似度閾値
            filters: フィルター条件

        Returns:
            List[Tuple[str, float]]: (コンテンツID, 類似度スコア)のリスト
        """

    @abstractmethod
    async def delete_embeddings(self, content_ids: List[str]) -> int:
        """
        埋め込みベクトルを削除

        Args:
            content_ids: 削除するコンテンツIDのリスト

        Returns:
            int: 削除された件数
        """

    @abstractmethod
    async def get_embedding_statistics(self) -> Dict[str, Any]:
        """
        埋め込み統計情報を取得

        Returns:
            Dict[str, Any]: 統計情報
        """
class CacheStorageAdapter(ABC):
    """キャッシュストレージアダプターの抽象基底クラス"""

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """
        キャッシュから値を取得

        Args:
            key: キー

        Returns:
            Optional[Any]: 値
        """

    @abstractmethod
    async def set(self, key: str, value: Any, ttl_seconds: int = None) -> None:
        """
        キャッシュに値を設定

        Args:
            key: キー
            value: 値
            ttl_seconds: 有効期限（秒）
        """

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        キャッシュから値を削除

        Args:
            key: キー

        Returns:
            bool: 削除成功フラグ
        """

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """
        キーが存在するかチェック

        Args:
            key: キー

        Returns:
            bool: 存在フラグ
        """

    @abstractmethod
    async def clear_pattern(self, pattern: str) -> int:
        """
        パターンにマッチするキーを削除

        Args:
            pattern: パターン

        Returns:
            int: 削除された件数
        """

    @abstractmethod
    async def get_cache_statistics(self) -> Dict[str, Any]:
        """
        キャッシュ統計情報を取得

        Returns:
            Dict[str, Any]: 統計情報
        """
class BaseStorageAdapter:
    """ストレージアダプター基底実装クラス"""

    def __init__(self, config: Dict[str, Any]):
        """
        初期化

        Args:
            config: 設定
        """
        self.config = config
        self._logger = logger
        self._connection = None
        self._is_connected = False

    async def connect(self) -> None:
        """接続を確立"""
        if not self._is_connected:
            try:
                await self._connect_impl()
                self._is_connected = True
                self._logger.info(f"{self.__class__.__name__}に接続しました")
            except Exception as e:
                self._logger.error(f"{self.__class__.__name__}への接続に失敗: {e}")
                raise

    async def disconnect(self) -> None:
        """接続を切断"""
        if self._is_connected:
            try:
                await self._disconnect_impl()
                self._is_connected = False
                self._logger.info(f"{self.__class__.__name__}から切断しました")
            except Exception as e:
                self._logger.error(f"{self.__class__.__name__}からの切断に失敗: {e}")
                raise

    async def health_check(self) -> Dict[str, Any]:
        """ヘルスチェック"""
        try:
            if not self._is_connected:
                return {"status": "disconnected", "message": "接続されていません"}

            health_info = await self._health_check_impl()
            return {"status": "healthy", "details": health_info}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    @abstractmethod
    async def _connect_impl(self) -> None:
        """接続実装（サブクラスで実装）"""

    @abstractmethod
    async def _disconnect_impl(self) -> None:
        """切断実装（サブクラスで実装）"""

    @abstractmethod
    async def _health_check_impl(self) -> Dict[str, Any]:
        """ヘルスチェック実装（サブクラスで実装）"""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._is_connected:
            # 同期的な切断（非推奨だが、コンテキストマネージャー用）
            import asyncio

            try:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(self.disconnect())
            except Exception as e:
                self._logger.error(f"コンテキストマネージャーでの切断に失敗: {e}")

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

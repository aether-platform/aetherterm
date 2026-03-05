"""セッションメモリ管理クラス"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from ..config.langchain_config import LangChainConfig
from ..config.memory_config import MemoryConfig
from ..models.session import SessionContext, SessionSummary, SessionType
from .hierarchical_memory import HierarchicalMemoryManager

logger = logging.getLogger(__name__)


class SessionMemoryManager:
    """セッションメモリ管理クラス。
    HierarchicalMemoryManagerを利用して、セッションコンテキストの保存、取得、クリーンアップを行います。
    """

    def __init__(
        self,
        langchain_config: LangChainConfig,
        memory_config: MemoryConfig,
        hierarchical_memory_manager: HierarchicalMemoryManager,
    ):
        """初期化

        Args:
            langchain_config: LangChain全体設定
            memory_config: メモリ固有設定
            hierarchical_memory_manager: 階層化メモリマネージャー
        """
        self.langchain_config = langchain_config
        self.memory_config = memory_config
        self.hierarchical_memory = hierarchical_memory_manager
        self._logger = logger

    async def create_session(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        session_type: SessionType = SessionType.TERMINAL,
        initial_metadata: Optional[Dict[str, Any]] = None,
    ) -> SessionContext:
        """新しいセッションを作成し、保存します。

        Args:
            session_id: 新しいセッションのID。
            user_id: ユーザーID。
            session_type: セッションタイプ。
            initial_metadata: 初期メタデータ。

        Returns:
            SessionContext: 作成されたセッションコンテキスト。
        """
        try:
            context = SessionContext(
                session_id=session_id,
                user_id=user_id,
                session_type=session_type,
                metadata=initial_metadata or {},
            )

            # SQLとRedisに保存
            await asyncio.gather(
                self.hierarchical_memory.sql_storage.store_session_context(context),
                self.hierarchical_memory.redis_storage.cache_session_context(context),
            )

            self._logger.info(f"新しいセッションを作成しました: {session_id} (user: {user_id})")
            return context

        except Exception as e:
            self._logger.error(f"セッション作成中にエラーが発生: {e}")
            raise

    async def get_session_context(self, session_id: str) -> Optional[SessionContext]:
        """セッションIDに基づいてセッションコンテキストを取得します。
        まずRedisキャッシュを試行し、次にSQLデータベースを試行します。

        Args:
            session_id: 取得するセッションのID。

        Returns:
            Optional[SessionContext]: 取得されたセッションコンテキスト、またはNone。
        """
        try:
            # まずRedisキャッシュから取得を試行
            context = await self.hierarchical_memory.redis_storage.get_session_context(session_id)
            if context:
                self._logger.debug(f"Redisキャッシュからセッションコンテキストを取得: {session_id}")
                return context

            # キャッシュにない場合はSQLから取得
            context = await self.hierarchical_memory.sql_storage.retrieve_session_context(
                session_id
            )
            if context:
                self._logger.debug(f"SQLからセッションコンテキストを取得: {session_id}")
                # 取得したコンテキストをRedisにキャッシュ
                await self.hierarchical_memory.redis_storage.cache_session_context(context)
                return context

            self._logger.info(f"セッションコンテキストが見つかりません: {session_id}")
            return None

        except Exception as e:
            self._logger.error(f"セッションコンテキスト取得中にエラーが発生: {e}")
            return None

    async def update_session_context(self, context: SessionContext) -> None:
        """セッションコンテキストを更新します。

        Args:
            context: 更新するセッションコンテキスト。
        """
        try:
            context.update_activity()  # 最終アクティビティを更新

            # SQLとRedisに保存
            await asyncio.gather(
                self.hierarchical_memory.sql_storage.store_session_context(context),
                self.hierarchical_memory.redis_storage.cache_session_context(context),
            )

            self._logger.debug(f"セッションコンテキストを更新しました: {context.session_id}")

        except Exception as e:
            self._logger.error(f"セッションコンテキスト更新中にエラーが発生: {e}")
            raise

    async def terminate_session(self, session_id: str, reason: Optional[str] = None) -> None:
        """セッションを終了状態に設定します。

        Args:
            session_id: 終了するセッションのID。
            reason: 終了理由。
        """
        try:
            context = await self.get_session_context(session_id)
            if context:
                context.terminate(reason)
                await self.update_session_context(context)
                self._logger.info(f"セッションを終了しました: {session_id} (Reason: {reason})")
            else:
                self._logger.warning(f"終了しようとしたセッションが見つかりません: {session_id}")

        except Exception as e:
            self._logger.error(f"セッション終了中にエラーが発生: {e}")
            raise

    async def list_active_sessions(self) -> List[SessionContext]:
        """現在アクティブなセッションのリストを取得します。

        Returns:
            List[SessionContext]: アクティブなセッションのリスト。
        """
        try:
            sessions = await self.hierarchical_memory.sql_storage.list_active_sessions()
            self._logger.info(f"アクティブなセッションを取得しました: {len(sessions)}件")
            return sessions

        except Exception as e:
            self._logger.error(f"アクティブセッションのリスト取得中にエラーが発生: {e}")
            return []

    async def cleanup_expired_sessions(self) -> int:
        """設定されたタイムアウトに基づいて期限切れのセッションをクリーンアップします。

        Returns:
            int: クリーンアップされたセッションの数。
        """
        try:
            timeout_minutes = (
                self.langchain_config.retention_days * 24 * 60
            )  # LangChainConfigの保持日数を分に変換

            deleted_count = await self.hierarchical_memory.sql_storage.cleanup_expired_sessions(
                timeout_minutes=timeout_minutes
            )

            # Redisからも古いセッションキャッシュを削除
            await self.hierarchical_memory.redis_storage.clear_pattern("session:*")

            self._logger.info(f"期限切れセッションをクリーンアップしました: {deleted_count}件")
            return deleted_count

        except Exception as e:
            self._logger.error(f"期限切れセッションのクリーンアップ中にエラーが発生: {e}")
            return 0

    async def get_session_summary(self, session_id: str) -> Optional[SessionSummary]:
        """特定のセッションの最新の要約を取得します。

        Args:
            session_id: 要約を取得するセッションのID。

        Returns:
            Optional[SessionSummary]: 最新のセッション要約、またはNone。
        """
        try:
            summaries = await self.hierarchical_memory.sql_storage.retrieve_summaries(
                session_id=session_id,
                summary_type="session",  # セッション要約のみ取得
            )

            if summaries:
                # 最新の要約を返す
                return sorted(summaries, key=lambda s: s.created_at, reverse=True)[0]

            return None

        except Exception as e:
            self._logger.error(f"セッション要約の取得中にエラーが発生: {e}")
            return None

    async def store_session_summary(self, summary: SessionSummary) -> str:
        """セッション要約を保存します。

        Args:
            summary: 保存するセッション要約。

        Returns:
            str: 保存された要約のID。
        """
        try:
            summary_id = await self.hierarchical_memory.sql_storage.store_summary(summary)
            self._logger.info(
                f"セッション要約を保存しました: {summary_id} (session: {summary.session_id})"
            )
            return summary_id

        except Exception as e:
            self._logger.error(f"セッション要約の保存中にエラーが発生: {e}")
            raise

    async def get_session_statistics(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """セッションに関する統計情報を取得します。

        Args:
            session_id: 統計情報を取得するセッションID。Noneの場合、全体の統計。

        Returns:
            Dict[str, Any]: 統計情報。
        """
        try:
            if session_id:
                context = await self.get_session_context(session_id)
                if context:
                    return context.get_activity_summary()
                return {"message": f"セッションが見つかりません: {session_id}"}
            # TODO: 全体統計を取得するロジックを実装
            active_sessions = await self.list_active_sessions()
            total_sessions = len(active_sessions)  # 簡易的な合計

            return {
                "total_active_sessions": total_sessions,
                "message": "全体統計は簡易版です。より詳細な統計は別途実装が必要です。",
            }

        except Exception as e:
            self._logger.error(f"セッション統計情報取得中にエラーが発生: {e}")
            return {"error": str(e)}

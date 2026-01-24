"""
会話メモリ管理クラス
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..config.langchain_config import LangChainConfig
from ..config.memory_config import MemoryConfig, MemoryStrategy
from ..models.conversation import ConversationEntry, ConversationType, MessageRole
from ..models.memory import MemoryEntry, MemoryType
from .hierarchical_memory import HierarchicalMemoryManager

logger = logging.getLogger(__name__)
class ConversationMemoryManager:
    """
    会話メモリ管理クラス。
    HierarchicalMemoryManagerを利用して、会話履歴の保存、取得、検索、クリーンアップを行います。
    """

    def __init__(
        self,
        langchain_config: LangChainConfig,
        memory_config: MemoryConfig,
        hierarchical_memory_manager: HierarchicalMemoryManager,
    ):
        """
        初期化

        Args:
            langchain_config: LangChain全体設定
            memory_config: メモリ固有設定
            hierarchical_memory_manager: 階層化メモリマネージャー
        """
        self.langchain_config = langchain_config
        self.memory_config = memory_config
        self.hierarchical_memory = hierarchical_memory_manager
        self._logger = logger

    async def store_conversation(
        self,
        session_id: str,
        content: str,
        conversation_type: ConversationType = ConversationType.USER_INPUT,
        role: MessageRole = MessageRole.USER,
        metadata: Optional[Dict[str, Any]] = None,
        parent_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        tokens: Optional[int] = None,
        model_name: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
        confidence_score: Optional[float] = None,
    ) -> str:
        """
        会話エントリを保存します。

        Args:
            session_id: セッションID。
            content: 会話内容。
            conversation_type: 会話タイプ。
            role: メッセージロール。
            metadata: 追加のメタデータ。
            parent_id: 親メッセージのID。
            thread_id: スレッドID。
            tokens: トークン数。
            model_name: 使用されたモデル名。
            processing_time_ms: 処理時間。
            confidence_score: 信頼度スコア。

        Returns:
            str: 保存されたエントリのID。
        """
        try:
            entry = ConversationEntry(
                session_id=session_id,
                conversation_type=conversation_type,
                role=role,
                content=content,
                metadata=metadata or {},
                parent_id=parent_id,
                thread_id=thread_id,
                tokens=tokens,
                model_name=model_name,
                processing_time_ms=processing_time_ms,
                confidence_score=confidence_score,
            )

            # ConversationEntryをMemoryEntryに変換し、階層化メモリに保存
            memory_entry = MemoryEntry(
                id=entry.id,
                session_id=entry.session_id,
                memory_type=MemoryType.MEDIUM_TERM,  # 会話は中期メモリに保存
                content=entry.content,
                content_type="text",
                priority=self._determine_priority(conversation_type),
                metadata=entry.to_dict(),  # ConversationEntry全体をメタデータとして保存
                created_at=entry.timestamp,
                updated_at=entry.timestamp,
                accessed_at=entry.timestamp,
                embedding=entry.embedding,  # 埋め込みはHierarchicalMemoryManagerで生成される
                embedding_model=self.langchain_config.embedding_model,
            )

            # 短期メモリにも保存（Redis）
            short_term_memory_entry = MemoryEntry(
                id=entry.id,
                session_id=entry.session_id,
                memory_type=MemoryType.SHORT_TERM,
                content=entry.content,
                content_type="text",
                priority=self._determine_priority(conversation_type),
                metadata=entry.to_dict(),
                created_at=entry.timestamp,
                updated_at=entry.timestamp,
                accessed_at=entry.timestamp,
                expires_at=datetime.utcnow()
                + timedelta(seconds=self.memory_config.short_term_ttl_seconds),
            )

            # 並列で保存
            await asyncio.gather(
                self.hierarchical_memory.store_memory_entry(memory_entry),
                self.hierarchical_memory.store_memory_entry(short_term_memory_entry),
            )

            self._logger.info(f"会話エントリを保存しました: {entry.id} (session: {session_id})")
            return str(entry.id)

        except Exception as e:
            self._logger.error(f"会話保存中にエラーが発生: {e}")
            raise

    async def retrieve_conversation_history(
        self, session_id: str, limit: int = 10, offset: int = 0, include_embeddings: bool = False
    ) -> List[ConversationEntry]:
        """
        特定のセッションの会話履歴を取得します。

        Args:
            session_id: セッションID。
            limit: 取得する会話エントリの最大数。
            offset: 取得を開始するオフセット。
            include_embeddings: 埋め込みベクトルを含めるかどうか。

        Returns:
            List[ConversationEntry]: 会話履歴のリスト。
        """
        try:
            # 主に中期メモリ（SQL）から取得
            # HierarchicalMemoryManagerのsearch_memoryを直接使うこともできるが、
            # 会話履歴は時系列順で取得することが多いため、SQLアダプターのretrieve_conversationsを直接利用
            conversations = await self.hierarchical_memory.sql_storage.retrieve_conversations(
                session_id=session_id, limit=limit, offset=offset
            )

            # 必要に応じて埋め込みを補完
            if include_embeddings:
                for conv in conversations:
                    if not conv.embedding:
                        # HierarchicalMemoryManager経由で埋め込みを取得
                        memory_entry = await self.hierarchical_memory.retrieve_memory_entry(
                            str(conv.id), MemoryType.LONG_TERM
                        )
                        if memory_entry and memory_entry.embedding:
                            conv.embedding = memory_entry.embedding

            self._logger.info(
                f"会話履歴を取得しました: {len(conversations)}件 (session: {session_id})"
            )
            return conversations

        except Exception as e:
            self._logger.error(f"会話履歴取得中にエラーが発生: {e}")
            return []

    async def search_similar_conversations(
        self,
        query: str,
        session_id: Optional[str] = None,
        limit: int = 5,
        threshold: Optional[float] = None,
        strategy: MemoryStrategy = MemoryStrategy.HYBRID,
    ) -> List[ConversationEntry]:
        """
        類似の会話エントリを検索します。

        Args:
            query: 検索クエリ。
            session_id: 検索を特定のセッションに限定する場合のセッションID。
            limit: 返す結果の最大数。
            threshold: 類似度スコアの閾値。
            strategy: 検索戦略。

        Returns:
            List[ConversationEntry]: 類似会話エントリのリスト。
        """
        try:
            search_result = await self.hierarchical_memory.search_memory(
                query=query,
                session_id=session_id,
                strategy=strategy,
                limit=limit,
                threshold=threshold,
            )

            conversations: List[ConversationEntry] = []
            for entry in search_result.entries:
                # MemoryEntryのメタデータからConversationEntryを復元
                if "conversation_type" in entry.metadata and "role" in entry.metadata:
                    try:
                        conv_entry = ConversationEntry.from_dict(entry.metadata)
                        conv_entry.embedding = entry.embedding  # 検索結果の埋め込みをセット
                        conversations.append(conv_entry)
                    except Exception as e:
                        self._logger.warning(f"MemoryEntryからConversationEntryへの変換に失敗: {e}")
                        continue

            self._logger.info(f"類似会話検索結果: {len(conversations)}件 (query: '{query}')")
            return conversations

        except Exception as e:
            self._logger.error(f"類似会話検索中にエラーが発生: {e}")
            return []

    async def cleanup_old_conversations(self) -> int:
        """
        設定された保持日数に基づいて古い会話データをクリーンアップします。

        Returns:
            int: 削除された会話エントリの総数。
        """
        try:
            # HierarchicalMemoryManagerのクリーンアップメソッドを呼び出す
            deleted_counts = await self.hierarchical_memory.cleanup_old_memory()

            total_deleted = sum(deleted_counts.values())
            self._logger.info(f"古い会話データをクリーンアップしました: {total_deleted}件")
            return total_deleted

        except Exception as e:
            self._logger.error(f"会話クリーンアップ中にエラーが発生: {e}")
            raise

    async def get_conversation_statistics(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        会話に関する統計情報を取得します。

        Args:
            session_id: 統計情報を取得するセッションID。Noneの場合、全体の統計。

        Returns:
            Dict[str, Any]: 統計情報。
        """
        try:
            if session_id:
                stats = await self.hierarchical_memory.sql_storage.get_conversation_statistics(
                    session_id
                )
            else:
                # TODO: 全体統計を取得するメソッドをSQLStorageAdapterに追加する必要がある
                stats = {"message": "全体統計は未実装です。セッションIDを指定してください。"}

            self._logger.info(f"会話統計情報を取得しました (session: {session_id}): {stats}")
            return stats

        except Exception as e:
            self._logger.error(f"会話統計情報取得中にエラーが発生: {e}")
            return {"error": str(e)}

    def _determine_priority(self, conversation_type: ConversationType) -> MemoryType:
        """会話タイプに基づいてメモリ優先度を決定します。"""
        if conversation_type in [ConversationType.ERROR_MESSAGE, ConversationType.SYSTEM_MESSAGE]:
            return MemoryType.LONG_TERM  # 重要な情報は長期メモリへ
        if conversation_type == ConversationType.USER_INPUT:
            return MemoryType.MEDIUM_TERM
        return MemoryType.SHORT_TERM  # AI応答やコマンド実行は短期・中期で十分な場合が多い

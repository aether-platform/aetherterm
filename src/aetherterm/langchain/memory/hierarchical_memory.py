"""階層化メモリマネージャー"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

from ..config.langchain_config import LangChainConfig
from ..config.memory_config import MemoryConfig, MemoryStrategy
from ..models.memory import (
    ContextEntry,
    MemoryEntry,
    MemorySearchResult,
    MemoryStatistics,
    MemoryType,
)
from ..storage.redis_adapter import RedisStorageAdapter
from ..storage.sql_adapter import SQLStorageAdapter
from ..storage.vector_adapter import VectorStoreAdapter

logger = logging.getLogger(__name__)


class HierarchicalMemoryManager:
    """階層化メモリ管理クラス。
    短期（Redis）、中期（SQL）、長期（Vector Store）のメモリを統合管理します。
    """

    def __init__(
        self,
        langchain_config: LangChainConfig,
        memory_config: MemoryConfig,
        redis_storage: RedisStorageAdapter,
        sql_storage: SQLStorageAdapter,
        vector_storage: VectorStoreAdapter,
    ):
        """初期化

        Args:
            langchain_config: LangChain全体設定
            memory_config: メモリ固有設定
            redis_storage: Redisストレージアダプター（短期メモリ）
            sql_storage: SQLストレージアダプター（中期メモリ）
            vector_storage: ベクトルストレージアダプター（長期メモリ）
        """
        self.langchain_config = langchain_config
        self.memory_config = memory_config
        self.redis_storage = redis_storage
        self.sql_storage = sql_storage
        self.vector_storage = vector_storage
        self._logger = logger

        self._is_initialized = False

    async def initialize(self) -> None:
        """メモリマネージャーを初期化し、すべてのストレージに接続します。"""
        if self._is_initialized:
            self._logger.info("HierarchicalMemoryManagerは既に初期化されています。")
            return

        self._logger.info("HierarchicalMemoryManagerを初期化中...")

        try:
            await asyncio.gather(
                self.redis_storage.connect(),
                self.sql_storage.connect(),
                self.vector_storage.connect(),
            )
            self._is_initialized = True
            self._logger.info("HierarchicalMemoryManagerの初期化が完了しました。")
        except Exception as e:
            self._logger.error(f"HierarchicalMemoryManagerの初期化に失敗: {e}")
            raise

    async def shutdown(self) -> None:
        """メモリマネージャーをシャットダウンし、すべてのストレージ接続を閉じます。"""
        if not self._is_initialized:
            self._logger.info("HierarchicalMemoryManagerは初期化されていません。")
            return

        self._logger.info("HierarchicalMemoryManagerをシャットダウン中...")

        try:
            await asyncio.gather(
                self.redis_storage.disconnect(),
                self.sql_storage.disconnect(),
                self.vector_storage.disconnect(),
            )
            self._is_initialized = False
            self._logger.info("HierarchicalMemoryManagerのシャットダウンが完了しました。")
        except Exception as e:
            self._logger.error(f"HierarchicalMemoryManagerのシャットダウンに失敗: {e}")
            raise

    async def store_memory_entry(self, entry: MemoryEntry) -> str:
        """メモリエントリを適切な階層に保存します。

        Args:
            entry: 保存するメモリエントリ。

        Returns:
            str: 保存されたエントリのID。
        """
        if not self._is_initialized:
            raise RuntimeError("MemoryManagerが初期化されていません。")

        try:
            if entry.memory_type == MemoryType.SHORT_TERM:
                # Redisに保存
                await self.redis_storage.set(
                    self._get_memory_key(entry),
                    entry.to_dict(),
                    ttl_seconds=self.memory_config.short_term_ttl_seconds,
                )
                self._logger.debug(f"短期メモリに保存: {entry.id}")
            elif entry.memory_type == MemoryType.MEDIUM_TERM:
                # SQLに保存
                await self.sql_storage.store_memory_entry(entry)
                self._logger.debug(f"中期メモリに保存: {entry.id}")
            elif entry.memory_type == MemoryType.LONG_TERM:
                # Vector Storeに保存
                if not entry.embedding:
                    entry.embedding = await self.vector_storage.generate_embedding(entry.content)
                    entry.embedding_model = self.langchain_config.embedding_model
                await self.vector_storage.store_embedding(
                    content_id=str(entry.id),
                    content=entry.content,
                    embedding=entry.embedding,
                    metadata=entry.metadata,
                )
                self._logger.debug(f"長期メモリに保存: {entry.id}")
            else:
                raise ValueError(f"不明なメモリタイプ: {entry.memory_type}")

            return str(entry.id)
        except Exception as e:
            self._logger.error(
                f"メモリエントリの保存に失敗 ({entry.id}, {entry.memory_type.value}): {e}"
            )
            raise

    async def retrieve_memory_entry(
        self, entry_id: str, memory_type: MemoryType
    ) -> Optional[MemoryEntry]:
        """指定されたIDとメモリタイプでメモリエントリを取得します。

        Args:
            entry_id: 取得するエントリのID。
            memory_type: 取得するエントリのメモリタイプ。

        Returns:
            Optional[MemoryEntry]: 取得されたメモリエントリ、またはNone。
        """
        if not self._is_initialized:
            raise RuntimeError("MemoryManagerが初期化されていません。")

        try:
            data = None
            if memory_type == MemoryType.SHORT_TERM:
                data = await self.redis_storage.get(
                    self._get_memory_key_by_id(entry_id, memory_type)
                )
            elif memory_type == MemoryType.MEDIUM_TERM:
                data = await self.sql_storage.retrieve_memory_entry(entry_id)
            elif memory_type == MemoryType.LONG_TERM:
                # 長期メモリからは直接IDで取得する機能は通常提供されない（検索が主）
                # ここでは簡易的に、SQLから取得できると仮定
                data = await self.sql_storage.retrieve_memory_entry(entry_id)

            if data:
                if isinstance(data, dict):
                    return MemoryEntry.from_dict(data)
                if isinstance(data, MemoryEntry):
                    return data
            return None
        except Exception as e:
            self._logger.error(f"メモリエントリの取得に失敗 ({entry_id}, {memory_type.value}): {e}")
            return None

    async def search_memory(
        self,
        query: str,
        session_id: Optional[str] = None,
        strategy: MemoryStrategy = MemoryStrategy.HYBRID,
        limit: int = 10,
        threshold: Optional[float] = None,
    ) -> MemorySearchResult:
        """階層化メモリ全体から関連する情報を検索します。

        Args:
            query: 検索クエリ。
            session_id: 検索を特定のセッションに限定する場合のセッションID。
            strategy: 検索戦略（SHORT_TERM, STRUCTURED, SEMANTIC, HYBRID）。
            limit: 返す結果の最大数。
            threshold: 類似度スコアの閾値。

        Returns:
            MemorySearchResult: 検索結果オブジェクト。
        """
        if not self._is_initialized:
            raise RuntimeError("MemoryManagerが初期化されていません。")

        start_time = datetime.utcnow()
        results: List[MemoryEntry] = []

        threshold = threshold or self.memory_config.similarity_threshold

        # 各ストレージからの検索タスクを並列実行
        tasks = []

        # 短期メモリ (Redis)
        if strategy in [MemoryStrategy.SHORT_TERM, MemoryStrategy.HYBRID]:
            tasks.append(self._search_short_term_memory(query, session_id, limit))

        # 中期メモリ (SQL)
        if strategy in [MemoryStrategy.STRUCTURED, MemoryStrategy.HYBRID]:
            tasks.append(self._search_medium_term_memory(query, session_id, limit))

        # 長期メモリ (Vector Store)
        if strategy in [MemoryStrategy.SEMANTIC, MemoryStrategy.HYBRID]:
            tasks.append(self._search_long_term_memory(query, session_id, limit, threshold))

        # 結果を収集
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in raw_results:
            if isinstance(res, list):
                results.extend(res)
            elif isinstance(res, Exception):
                self._logger.warning(f"メモリ検索中にエラーが発生: {res}")

        # 重複排除とランキング
        unique_results = self._deduplicate_and_rank_memory_entries(results, query)

        # 最終的な結果を制限
        final_results = unique_results[:limit]

        end_time = datetime.utcnow()
        search_time_ms = int((end_time - start_time).total_seconds() * 1000)

        self._logger.info(
            f"メモリ検索が完了しました。結果数: {len(final_results)}, 処理時間: {search_time_ms}ms"
        )

        return MemorySearchResult(
            entries=final_results,
            total_count=len(final_results),
            search_time_ms=search_time_ms,
            query=query,
            filters={"session_id": session_id, "strategy": strategy.value, "threshold": threshold},
        )

    async def _search_short_term_memory(
        self, query: str, session_id: Optional[str], limit: int
    ) -> List[MemoryEntry]:
        """短期メモリ（Redis）を検索"""
        found_entries: List[MemoryEntry] = []

        # Redisの最近の会話キャッシュから検索
        recent_conversations = await self.redis_storage.get_recent_conversations(
            session_id or "global", limit=limit
        )

        for conv in recent_conversations:
            # 簡易的なキーワードマッチング
            if query.lower() in conv.content.lower():
                found_entries.append(
                    MemoryEntry(
                        id=conv.id,
                        session_id=conv.session_id,
                        memory_type=MemoryType.SHORT_TERM,
                        content=conv.content,
                        created_at=conv.timestamp,
                        relevance_score=0.8,  # 高い関連度を仮定
                    )
                )
        return found_entries

    async def _search_medium_term_memory(
        self, query: str, session_id: Optional[str], limit: int
    ) -> List[MemoryEntry]:
        """中期メモリ（SQL）を検索"""
        # SQLStorageAdapterのsearch_conversationsを呼び出す
        conversations = await self.sql_storage.search_conversations(
            query=query, session_id=session_id, limit=limit
        )

        entries = []
        for conv in conversations:
            entries.append(
                MemoryEntry(
                    id=conv.id,
                    session_id=conv.session_id,
                    memory_type=MemoryType.MEDIUM_TERM,
                    content=conv.content,
                    created_at=conv.timestamp,
                    relevance_score=0.6,  # 中程度の関連度を仮定
                )
            )
        return entries

    async def _search_long_term_memory(
        self, query: str, session_id: Optional[str], limit: int, threshold: float
    ) -> List[MemoryEntry]:
        """長期メモリ（Vector Store）を検索"""
        filters = {}
        if session_id:
            filters["session_id"] = session_id

        results = await self.vector_storage.similarity_search(
            query=query, limit=limit, threshold=threshold, filters=filters
        )

        entries = []
        for content_id, score in results:
            # ここではcontent_idから元のコンテンツを復元する必要がある
            # 簡易的に、SQLから取得できると仮定
            original_entry = await self.sql_storage.retrieve_memory_entry(content_id)
            if original_entry:
                entries.append(
                    MemoryEntry(
                        id=original_entry.id,
                        session_id=original_entry.session_id,
                        memory_type=MemoryType.LONG_TERM,
                        content=original_entry.content,
                        created_at=original_entry.created_at,
                        relevance_score=score,
                    )
                )
        return entries

    def _deduplicate_and_rank_memory_entries(
        self, entries: List[MemoryEntry], query: str
    ) -> List[MemoryEntry]:
        """メモリエントリの重複を排除し、関連度でランキングします。

        Args:
            entries: 処理するメモリエントリのリスト。
            query: 元の検索クエリ（ランキングに使用）。

        Returns:
            List[MemoryEntry]: 重複排除され、ランキングされたメモリエントリのリスト。
        """
        unique_entries: Dict[str, MemoryEntry] = {}
        for entry in entries:
            # IDをキーとして重複排除
            if (
                str(entry.id) not in unique_entries
                or entry.relevance_score > unique_entries[str(entry.id)].relevance_score
            ):
                unique_entries[str(entry.id)] = entry

        # 関連度スコアでソート
        sorted_entries = sorted(
            unique_entries.values(), key=lambda x: x.relevance_score, reverse=True
        )

        return sorted_entries

    def _get_memory_key(self, entry: MemoryEntry) -> str:
        """メモリエントリのキーを生成"""
        return f"{entry.memory_type.value}:{entry.session_id}:{entry.id}"

    def _get_memory_key_by_id(self, entry_id: str, memory_type: MemoryType) -> str:
        """IDとメモリタイプからメモリエントリのキーを生成"""
        # この関数は、Redisから直接IDで取得する場合に必要
        # Redisのキー設計に依存するため、ここでは簡易的に実装
        # 実際には、Redisに保存する際にセッションIDもキーに含めるべき
        return (
            f"{memory_type.value}:*:*:{entry_id}"  # ワイルドカードはRedisのgetでは使えないので注意
        )

    async def get_memory_statistics(self) -> MemoryStatistics:
        """階層化メモリ全体の統計情報を取得します。

        Returns:
            MemoryStatistics: メモリ統計情報オブジェクト。
        """
        if not self._is_initialized:
            raise RuntimeError("MemoryManagerが初期化されていません。")

        stats = MemoryStatistics()

        # 各ストレージから統計情報を取得
        redis_stats_task = self.redis_storage.get_cache_statistics()
        sql_stats_task = self.sql_storage.get_conversation_statistics(
            "dummy_session_id"
        )  # TODO: 全体統計を取得するメソッドが必要
        vector_stats_task = self.vector_storage.get_embedding_statistics()

        redis_stats, sql_stats, vector_stats = await asyncio.gather(
            redis_stats_task, sql_stats_task, vector_stats_task, return_exceptions=True
        )

        # Redis統計
        if isinstance(redis_stats, dict):
            stats.entries_by_type[MemoryType.SHORT_TERM.value] = redis_stats.get("total_keys", 0)
            stats.total_entries += redis_stats.get("total_keys", 0)
            # Redisのメモリ使用量をバイト単位で加算
            stats.total_size_bytes += redis_stats.get("used_memory", 0)
        else:
            self._logger.warning(f"Redis統計情報の取得に失敗: {redis_stats}")

        # SQL統計
        if isinstance(sql_stats, dict):
            stats.entries_by_type[MemoryType.MEDIUM_TERM.value] = sql_stats.get(
                "total_conversations", 0
            )
            stats.total_entries += sql_stats.get("total_conversations", 0)
            # SQLのサイズは別途計算が必要
        else:
            self._logger.warning(f"SQL統計情報の取得に失敗: {sql_stats}")

        # Vector Store統計
        if isinstance(vector_stats, dict):
            stats.entries_by_type[MemoryType.LONG_TERM.value] = vector_stats.get(
                "total_documents", 0
            )
            stats.total_entries += vector_stats.get("total_documents", 0)
            # Vector Storeのサイズは別途計算が必要
        else:
            self._logger.warning(f"Vector Store統計情報の取得に失敗: {vector_stats}")

        # TODO: 平均関連度スコア、最もアクセスされたエントリ、最古/最新エントリの計算

        self._logger.info(f"メモリ統計情報を取得しました: {stats.total_entries}件")
        return stats

    async def cleanup_old_memory(self) -> Dict[str, int]:
        """設定に基づいて古いメモリエントリをクリーンアップします。

        Returns:
            Dict[str, int]: 各メモリタイプで削除されたエントリ数。
        """
        if not self._is_initialized:
            raise RuntimeError("MemoryManagerが初期化されていません。")

        deleted_counts = {
            MemoryType.SHORT_TERM.value: 0,
            MemoryType.MEDIUM_TERM.value: 0,
            MemoryType.LONG_TERM.value: 0,
        }

        # 短期メモリのクリーンアップ (RedisはTTLで自動)
        # RedisStorageAdapterのcleanup_old_cacheはTTLが設定されていないキーを対象とするため、
        # ここでは直接呼び出す必要はないが、念のため含める
        deleted_counts[MemoryType.SHORT_TERM.value] += await self.redis_storage.cleanup_old_cache()

        # 中期メモリのクリーンアップ
        deleted_counts[
            MemoryType.MEDIUM_TERM.value
        ] += await self.sql_storage.delete_old_conversations(self.memory_config.medium_term_days)

        # 長期メモリのクリーンアップ (Vector Store)
        # Vector Storeのクリーンアップは、SQLの会話IDに基づいて行う
        # TODO: SQLから古い会話IDを取得し、それらの埋め込みをVector Storeから削除するロジックが必要
        # 現状はSQLの削除件数を長期メモリの削除件数として仮定
        deleted_counts[MemoryType.LONG_TERM.value] += await self.vector_storage.delete_embeddings(
            []
        )  # ダミー呼び出し

        self._logger.info(f"古いメモリのクリーンアップが完了しました: {deleted_counts}")
        return deleted_counts

    async def get_context_entries(
        self,
        query: str,
        session_id: Optional[str] = None,
        limit: int = 5,
        strategy: MemoryStrategy = MemoryStrategy.HYBRID,
    ) -> List[ContextEntry]:
        """検索結果からContextEntryのリストを生成します。

        Args:
            query: 検索クエリ。
            session_id: セッションID。
            limit: 取得するコンテキストエントリの最大数。
            strategy: 検索戦略。

        Returns:
            List[ContextEntry]: 関連するコンテキストエントリのリスト。
        """
        search_result = await self.search_memory(
            query=query, session_id=session_id, strategy=strategy, limit=limit
        )

        context_entries: List[ContextEntry] = []
        for entry in search_result.entries:
            context_entries.append(
                ContextEntry(
                    content=entry.content,
                    source=entry.memory_type.value,
                    relevance_score=entry.relevance_score,
                    timestamp=entry.created_at,
                    metadata=entry.metadata,
                    source_id=str(entry.id),
                    memory_type=entry.memory_type,
                    tags=entry.tags,
                )
            )

        return context_entries

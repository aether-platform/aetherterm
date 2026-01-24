"""
ログ処理統合マネージャー

3層ストレージ戦略でのターミナルログ処理を統合管理
"""

import asyncio
import logging
from typing import Dict, List, Optional

from ..langchain.config.storage_config import StorageConfig
from ..langchain.memory.hierarchical_memory import HierarchicalMemoryManager
from ..langchain.storage.redis_adapter import RedisStorageAdapter
from ..langchain.storage.sql_adapter import SQLStorageAdapter
from ..langchain.storage.vector_adapter import VectorStoreAdapter
from .log_processor import LogProcessor
from .structured_extractor import StructuredExtractor
from .terminal_log_capture import TerminalLogCapture

logger = logging.getLogger(__name__)
def get_log_processing_manager() -> "LogProcessingManager":
    """
    ログ処理マネージャーのインスタンスを取得

    Note: This is a compatibility function. In a proper DI setup,
    this should be obtained from the container.
    """
    from ..core.container import DIContainer

    try:
        return DIContainer.get_log_processing_manager()
    except Exception as e:
        logger.warning(f"Failed to get log processing manager from DI container: {e}")
        # Create a default instance as fallback
        from ..langchain.config.storage_config import StorageConfig

        default_config = StorageConfig()
        return LogProcessingManager(default_config)
class LogProcessingManager:
    """ログ処理統合マネージャークラス"""

    def __init__(
        self,
        storage_config: StorageConfig,
        hierarchical_memory: Optional[HierarchicalMemoryManager] = None,
    ):
        """
        初期化

        Args:
            storage_config: ストレージ設定
            hierarchical_memory: 既存の階層化メモリマネージャー（オプション）
        """
        self.storage_config = storage_config
        self._logger = logger
        self._running = False

        # 既存の階層化メモリシステムを活用
        if hierarchical_memory:
            self.hierarchical_memory = hierarchical_memory
            self.redis_storage = hierarchical_memory.redis_storage
            self.sql_storage = hierarchical_memory.sql_storage
            self.vector_storage = hierarchical_memory.vector_storage
        else:
            # 新規作成
            self.redis_storage = RedisStorageAdapter(storage_config)
            self.sql_storage = SQLStorageAdapter(storage_config)
            self.vector_storage = VectorStoreAdapter(storage_config)
            self.hierarchical_memory = None

        # ログ処理コンポーネント
        self.terminal_capture = TerminalLogCapture(self.redis_storage)
        self.log_processor = LogProcessor(self.redis_storage, self.sql_storage)
        self.structured_extractor = StructuredExtractor(self.sql_storage, self.vector_storage)

        # 実行中タスク管理
        self._processing_tasks: List[asyncio.Task] = []

    async def initialize(self) -> None:
        """ログ処理システム全体を初期化"""
        self._logger.info("Initializing LogProcessingManager...")

        try:
            # ストレージ接続
            if self.hierarchical_memory:
                await self.hierarchical_memory.initialize()
            else:
                await asyncio.gather(
                    self.redis_storage.connect(),
                    self.sql_storage.connect(),
                    self.vector_storage.connect(),
                )

            # コンポーネント初期化
            await asyncio.gather(
                self.terminal_capture.initialize(),
                self.log_processor.initialize(),
                self.structured_extractor.initialize(),
            )

            self._logger.info("LogProcessingManager initialization complete")

        except Exception as e:
            self._logger.error(f"Failed to initialize LogProcessingManager: {e}")
            raise

    async def start_processing(
        self,
        log_processing_interval: int = 10,
        pattern_extraction_interval: int = 300,
    ) -> None:
        """
        ログ処理を開始

        Args:
            log_processing_interval: ログ処理間隔（秒）
            pattern_extraction_interval: パターン抽出間隔（秒）
        """
        if self._running:
            self._logger.warning("LogProcessingManager is already running")
            return

        self._running = True
        self._logger.info("Starting pure Pub/Sub log processing system...")

        try:
            # バックグラウンドタスクを開始 (純粋Pub/Sub)
            self._processing_tasks = [
                asyncio.create_task(
                    self.log_processor.start_processing(),  # ポーリング間隔不要
                    name="log_processor_pubsub",
                ),
                asyncio.create_task(
                    self.structured_extractor.start_extraction(pattern_extraction_interval),
                    name="pattern_extractor",
                ),
            ]

            self._logger.info("Pure Pub/Sub log processing system started successfully")

            # タスクの完了を待機
            await asyncio.gather(*self._processing_tasks, return_exceptions=True)

        except Exception as e:
            self._logger.error(f"Log processing system error: {e}")
        finally:
            await self.stop_processing()

    async def stop_processing(self) -> None:
        """ログ処理を停止"""
        if not self._running:
            return

        self._logger.info("Stopping log processing system...")
        self._running = False

        # バックグラウンドタスクを停止
        await self.log_processor.stop_processing()
        await self.structured_extractor.stop_extraction()

        # タスクキャンセル
        for task in self._processing_tasks:
            if not task.done():
                task.cancel()

        # タスク完了待機
        if self._processing_tasks:
            await asyncio.gather(*self._processing_tasks, return_exceptions=True)
            self._processing_tasks.clear()

        self._logger.info("Log processing system stopped")

    async def add_terminal(self, terminal_id: str, log_file_path: str) -> None:
        """
        新しいターミナルを監視対象に追加

        Args:
            terminal_id: ターミナルの一意識別子
            log_file_path: 監視するログファイルパス
        """
        try:
            await self.terminal_capture.add_terminal(terminal_id, log_file_path)
            self._logger.info(f"Added terminal to processing: {terminal_id}")
        except Exception as e:
            self._logger.error(f"Failed to add terminal {terminal_id}: {e}")
            raise

    async def remove_terminal(self, terminal_id: str) -> None:
        """
        ターミナルを監視対象から削除

        Args:
            terminal_id: 削除するターミナルID
        """
        try:
            await self.terminal_capture.remove_terminal(terminal_id)
            self._logger.info(f"Removed terminal from processing: {terminal_id}")
        except Exception as e:
            self._logger.error(f"Failed to remove terminal {terminal_id}: {e}")

    async def get_recent_logs(self, terminal_id: str, limit: int = 100) -> List[Dict]:
        """Redis短期メモリから最近のログを取得"""
        try:
            return await self.terminal_capture.get_recent_logs(terminal_id, limit)
        except Exception as e:
            self._logger.error(f"Failed to get recent logs for {terminal_id}: {e}")
            return []

    async def search_structured_logs(
        self,
        query: str,
        terminal_id: Optional[str] = None,
        error_level: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """SQL中期メモリから構造化ログを検索"""
        try:
            return await self.log_processor.search_logs(
                query=query,
                terminal_id=terminal_id,
                error_level=error_level,
                limit=limit,
            )
        except Exception as e:
            self._logger.error(f"Failed to search structured logs: {e}")
            return []

    async def search_patterns(
        self,
        query_text: str,
        pattern_category: Optional[str] = None,
        limit: int = 10,
        threshold: float = 0.7,
    ) -> List:
        """VectorDB長期メモリからパターンを検索"""
        try:
            return await self.structured_extractor.search_similar_patterns(
                query_text=query_text,
                pattern_category=pattern_category,
                limit=limit,
                threshold=threshold,
            )
        except Exception as e:
            self._logger.error(f"Failed to search patterns: {e}")
            return []

    def initialize_terminal_capture(self, session_id: str) -> bool:
        """
        ターミナルキャプチャの初期化

        Args:
            session_id: セッションID

        Returns:
            bool: 初期化成功かどうか
        """
        try:
            if not self.terminal_capture:
                self._logger.error("Terminal capture not initialized")
                return False

            # セッションを追跡用に登録
            self._logger.info(f"Initializing terminal capture for session: {session_id}")
            return True

        except Exception as e:
            self._logger.error(f"Failed to initialize terminal capture for {session_id}: {e}")
            return False

    def capture_terminal_output(self, session_id: str, data: str) -> None:
        """
        ターミナル出力をキャプチャ

        Args:
            session_id: セッションID
            data: ターミナル出力データ
        """
        try:
            if not self.terminal_capture:
                self._logger.warning("Terminal capture not initialized, skipping output capture")
                return

            # 非同期でキャプチャ処理を実行
            asyncio.create_task(self.terminal_capture.capture_output(session_id, data))

        except Exception as e:
            self._logger.error(f"Failed to capture terminal output for {session_id}: {e}")

    async def get_terminal_summary(self, terminal_id: str) -> Dict:
        """指定ターミナルの包括的サマリーを取得"""
        try:
            # 各層からデータを取得
            recent_logs = await self.get_recent_logs(terminal_id, 10)
            log_summary = await self.log_processor.get_terminal_log_summary(terminal_id)
            terminal_stats = await self.terminal_capture.get_terminal_statistics(terminal_id)

            return {
                "terminal_id": terminal_id,
                "recent_activity": {
                    "log_count": len(recent_logs),
                    "latest_logs": recent_logs[:5],  # 最新5件
                },
                "structured_summary": log_summary,
                "capture_statistics": terminal_stats,
                "active_terminals": await self.terminal_capture.get_active_terminals(),
            }

        except Exception as e:
            self._logger.error(f"Failed to get terminal summary for {terminal_id}: {e}")
            return {"terminal_id": terminal_id, "error": str(e)}

    async def get_system_statistics(self) -> Dict:
        """システム全体の統計情報を取得"""
        try:
            pattern_stats = await self.structured_extractor.get_pattern_statistics()
            active_terminals = await self.terminal_capture.get_active_terminals()

            return {
                "active_terminals": {
                    "count": len(active_terminals),
                    "terminal_ids": active_terminals,
                },
                "pattern_analysis": pattern_stats,
                "system_status": {
                    "processing_active": self._running,
                    "background_tasks": len(self._processing_tasks),
                },
            }

        except Exception as e:
            self._logger.error(f"Failed to get system statistics: {e}")
            return {"error": str(e)}

    async def process_immediate_query(self, query: str, terminal_id: Optional[str] = None) -> Dict:
        """
        即座にクエリ処理（3層ストレージから総合的に検索）

        Args:
            query: 検索クエリ
            terminal_id: 対象ターミナルID（オプション）

        Returns:
            3層ストレージからの統合検索結果
        """
        try:
            # 並列で3層から検索
            recent_task = asyncio.create_task(
                self.get_recent_logs(terminal_id, 20) if terminal_id else asyncio.sleep(0)
            )
            structured_task = asyncio.create_task(
                self.search_structured_logs(query, terminal_id, limit=20)
            )
            pattern_task = asyncio.create_task(self.search_patterns(query, limit=10))

            recent_logs, structured_logs, patterns = await asyncio.gather(
                recent_task, structured_task, pattern_task, return_exceptions=True
            )

            return {
                "query": query,
                "terminal_id": terminal_id,
                "results": {
                    "recent_logs": recent_logs if not isinstance(recent_logs, Exception) else [],
                    "structured_logs": structured_logs
                    if not isinstance(structured_logs, Exception)
                    else [],
                    "patterns": patterns if not isinstance(patterns, Exception) else [],
                },
                "summary": {
                    "total_recent": len(recent_logs)
                    if not isinstance(recent_logs, Exception)
                    else 0,
                    "total_structured": len(structured_logs)
                    if not isinstance(structured_logs, Exception)
                    else 0,
                    "total_patterns": len(patterns) if not isinstance(patterns, Exception) else 0,
                },
            }

        except Exception as e:
            self._logger.error(f"Failed to process immediate query: {e}")
            return {"query": query, "error": str(e)}

    async def shutdown(self) -> None:
        """ログ処理システム全体をシャットダウン"""
        self._logger.info("Shutting down LogProcessingManager...")

        try:
            # 処理停止
            await self.stop_processing()

            # コンポーネントシャットダウン
            await self.terminal_capture.shutdown()

            # ストレージ切断
            if self.hierarchical_memory:
                await self.hierarchical_memory.shutdown()
            else:
                await asyncio.gather(
                    self.redis_storage.disconnect(),
                    self.sql_storage.disconnect(),
                    self.vector_storage.disconnect(),
                    return_exceptions=True,
                )

            self._logger.info("LogProcessingManager shutdown complete")

        except Exception as e:
            self._logger.error(f"Error during LogProcessingManager shutdown: {e}")

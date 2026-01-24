"""
構造化抽出器

SQL中期メモリから重要パターンを抽出し、VectorDB長期メモリに保存
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from ..langchain.storage.sql_adapter import SQLStorageAdapter
from ..langchain.storage.vector_adapter import VectorStoreAdapter

logger = logging.getLogger(__name__)
class StructuredExtractor:
    """構造化データ抽出クラス"""

    def __init__(
        self,
        sql_storage: SQLStorageAdapter,
        vector_storage: VectorStoreAdapter,
    ):
        """
        初期化

        Args:
            sql_storage: SQL中期メモリストレージ
            vector_storage: VectorDB長期メモリストレージ
        """
        self.sql_storage = sql_storage
        self.vector_storage = vector_storage
        self._logger = logger
        self._running = False

        # パターン抽出設定
        self.pattern_config = {
            "min_frequency": 3,  # 最小出現回数
            "time_window_hours": 24,  # 分析対象期間
            "min_similarity_threshold": 0.8,  # 類似度閾値
            "max_patterns_per_batch": 50,  # バッチあたり最大パターン数
        }

    async def initialize(self) -> None:
        """抽出器初期化"""
        if not await self.vector_storage.is_connected():
            await self.vector_storage.connect()

        # パターンコレクション設定
        await self._setup_pattern_collection()

        self._logger.info("StructuredExtractor initialized")

    async def _setup_pattern_collection(self) -> None:
        """パターン用VectorDBコレクション設定"""
        # 既存VectorStoreAdapterを活用し、パターン専用メタデータで管理
        try:
            # 統計情報取得でコレクション確認
            stats = await self.vector_storage.get_embedding_statistics()
            self._logger.info(f"Pattern collection ready: {stats}")
        except Exception as e:
            self._logger.error(f"Failed to setup pattern collection: {e}")
            raise

    async def start_extraction(self, extraction_interval: int = 300) -> None:
        """
        パターン抽出を開始

        Args:
            extraction_interval: 抽出間隔（秒）
        """
        if self._running:
            self._logger.warning("StructuredExtractor is already running")
            return

        self._running = True
        self._logger.info("Starting pattern extraction...")

        try:
            while self._running:
                await self._extract_patterns()
                await asyncio.sleep(extraction_interval)
        except Exception as e:
            self._logger.error(f"Pattern extraction error: {e}")
        finally:
            self._running = False
            self._logger.info("Pattern extraction stopped")

    async def stop_extraction(self) -> None:
        """パターン抽出停止"""
        self._running = False

    async def _extract_patterns(self) -> None:
        """パターン抽出処理"""
        try:
            # エラーパターン抽出
            error_patterns = await self._extract_error_patterns()
            await self._save_patterns(error_patterns, "ERROR_PATTERN")

            # コマンドパターン抽出
            command_patterns = await self._extract_command_patterns()
            await self._save_patterns(command_patterns, "COMMAND_PATTERN")

            # 出力パターン抽出
            output_patterns = await self._extract_output_patterns()
            await self._save_patterns(output_patterns, "OUTPUT_PATTERN")

            self._logger.info(
                f"Extracted patterns: {len(error_patterns)} errors, "
                f"{len(command_patterns)} commands, {len(output_patterns)} outputs"
            )

        except Exception as e:
            self._logger.error(f"Failed to extract patterns: {e}")

    async def _extract_error_patterns(self) -> List[Dict[str, Any]]:
        """エラーパターン抽出"""
        time_threshold = datetime.utcnow() - timedelta(
            hours=self.pattern_config["time_window_hours"]
        )

        error_sql = """
        SELECT 
            output_text,
            error_level,
            COUNT(*) as frequency,
            GROUP_CONCAT(DISTINCT terminal_id) as terminal_ids,
            MIN(timestamp) as first_seen,
            MAX(timestamp) as last_seen
        FROM terminal_logs 
        WHERE error_level IN ('ERROR', 'WARNING')
        AND timestamp > ?
        GROUP BY output_text, error_level
        HAVING COUNT(*) >= ?
        ORDER BY frequency DESC
        LIMIT ?
        """

        try:
            results = await self.sql_storage.fetch_all(
                error_sql,
                [
                    time_threshold.isoformat(),
                    self.pattern_config["min_frequency"],
                    self.pattern_config["max_patterns_per_batch"],
                ],
            )

            patterns = []
            for row in results:
                pattern = {
                    "content": row["output_text"],
                    "error_level": row["error_level"],
                    "frequency": row["frequency"],
                    "terminal_ids": row["terminal_ids"].split(","),
                    "first_seen": row["first_seen"],
                    "last_seen": row["last_seen"],
                    "pattern_type": "ERROR",
                    "severity_score": self._calculate_severity_score(row),
                }
                patterns.append(pattern)

            return patterns

        except Exception as e:
            self._logger.error(f"Failed to extract error patterns: {e}")
            return []

    async def _extract_command_patterns(self) -> List[Dict[str, Any]]:
        """コマンドパターン抽出"""
        time_threshold = datetime.utcnow() - timedelta(
            hours=self.pattern_config["time_window_hours"]
        )

        command_sql = """
        SELECT 
            command,
            COUNT(*) as frequency,
            GROUP_CONCAT(DISTINCT terminal_id) as terminal_ids,
            COUNT(CASE WHEN error_level = 'ERROR' THEN 1 END) as error_count,
            COUNT(CASE WHEN error_level = 'INFO' THEN 1 END) as success_count,
            MIN(timestamp) as first_seen,
            MAX(timestamp) as last_seen
        FROM terminal_logs 
        WHERE log_type = 'COMMAND'
        AND command IS NOT NULL
        AND timestamp > ?
        GROUP BY command
        HAVING COUNT(*) >= ?
        ORDER BY frequency DESC
        LIMIT ?
        """

        try:
            results = await self.sql_storage.fetch_all(
                command_sql,
                [
                    time_threshold.isoformat(),
                    self.pattern_config["min_frequency"],
                    self.pattern_config["max_patterns_per_batch"],
                ],
            )

            patterns = []
            for row in results:
                pattern = {
                    "content": row["command"],
                    "frequency": row["frequency"],
                    "terminal_ids": row["terminal_ids"].split(","),
                    "error_count": row["error_count"],
                    "success_count": row["success_count"],
                    "success_rate": row["success_count"] / row["frequency"]
                    if row["frequency"] > 0
                    else 0,
                    "first_seen": row["first_seen"],
                    "last_seen": row["last_seen"],
                    "pattern_type": "COMMAND",
                    "risk_score": self._calculate_command_risk_score(row),
                }
                patterns.append(pattern)

            return patterns

        except Exception as e:
            self._logger.error(f"Failed to extract command patterns: {e}")
            return []

    async def _extract_output_patterns(self) -> List[Dict[str, Any]]:
        """出力パターン抽出"""
        time_threshold = datetime.utcnow() - timedelta(
            hours=self.pattern_config["time_window_hours"]
        )

        # 長い出力や頻出する出力パターンを抽出
        output_sql = """
        SELECT 
            SUBSTR(output_text, 1, 200) as output_sample,
            LENGTH(output_text) as output_length,
            COUNT(*) as frequency,
            error_level,
            GROUP_CONCAT(DISTINCT terminal_id) as terminal_ids,
            MIN(timestamp) as first_seen,
            MAX(timestamp) as last_seen
        FROM terminal_logs 
        WHERE log_type = 'OUTPUT'
        AND LENGTH(output_text) > 100
        AND timestamp > ?
        GROUP BY SUBSTR(output_text, 1, 200), error_level
        HAVING COUNT(*) >= ?
        ORDER BY frequency DESC, output_length DESC
        LIMIT ?
        """

        try:
            results = await self.sql_storage.fetch_all(
                output_sql,
                [
                    time_threshold.isoformat(),
                    self.pattern_config["min_frequency"],
                    self.pattern_config["max_patterns_per_batch"],
                ],
            )

            patterns = []
            for row in results:
                pattern = {
                    "content": row["output_sample"],
                    "output_length": row["output_length"],
                    "frequency": row["frequency"],
                    "error_level": row["error_level"],
                    "terminal_ids": row["terminal_ids"].split(","),
                    "first_seen": row["first_seen"],
                    "last_seen": row["last_seen"],
                    "pattern_type": "OUTPUT",
                    "complexity_score": self._calculate_output_complexity(row),
                }
                patterns.append(pattern)

            return patterns

        except Exception as e:
            self._logger.error(f"Failed to extract output patterns: {e}")
            return []

    def _calculate_severity_score(self, error_data: Dict[str, Any]) -> float:
        """エラーの重要度スコア計算"""
        base_score = 0.5

        # 頻度による加算
        frequency_factor = min(error_data["frequency"] / 10.0, 1.0)

        # エラーレベルによる加算
        level_factor = 1.0 if error_data["error_level"] == "ERROR" else 0.7

        # ターミナル数による加算
        terminal_count = len(error_data["terminal_ids"])
        spread_factor = min(terminal_count / 5.0, 1.0)

        return min(
            base_score + (frequency_factor * 0.3) + (level_factor * 0.3) + (spread_factor * 0.2),
            1.0,
        )

    def _calculate_command_risk_score(self, command_data: Dict[str, Any]) -> float:
        """コマンドのリスクスコア計算"""
        if command_data["frequency"] == 0:
            return 0.0

        error_rate = command_data["error_count"] / command_data["frequency"]
        frequency_factor = min(command_data["frequency"] / 20.0, 1.0)

        # 危険なコマンドキーワードチェック
        dangerous_keywords = ["rm -rf", "dd if=", "mkfs", "format", "sudo", "chmod 777"]
        keyword_factor = 0.0
        for keyword in dangerous_keywords:
            if keyword in command_data["content"].lower():
                keyword_factor = 0.8
                break

        return min(error_rate * 0.4 + frequency_factor * 0.3 + keyword_factor, 1.0)

    def _calculate_output_complexity(self, output_data: Dict[str, Any]) -> float:
        """出力の複雑度スコア計算"""
        # 長さによる複雑度
        length_factor = min(output_data["output_length"] / 1000.0, 1.0)

        # 頻度による重要度
        frequency_factor = min(output_data["frequency"] / 15.0, 1.0)

        return length_factor * 0.6 + frequency_factor * 0.4

    async def _save_patterns(self, patterns: List[Dict[str, Any]], pattern_category: str) -> None:
        """パターンをVectorDBに保存"""
        for pattern in patterns:
            try:
                # パターン内容をベクトル化対象のテキストとして準備
                content_for_embedding = self._prepare_content_for_embedding(pattern)

                # メタデータ準備
                metadata = {
                    "pattern_category": pattern_category,
                    "pattern_type": pattern.get("pattern_type", "UNKNOWN"),
                    "frequency": pattern.get("frequency", 0),
                    "error_level": pattern.get("error_level", "UNKNOWN"),
                    "terminal_count": len(pattern.get("terminal_ids", [])),
                    "first_seen": pattern.get("first_seen", ""),
                    "last_seen": pattern.get("last_seen", ""),
                    "severity_score": pattern.get("severity_score", 0.0),
                    "risk_score": pattern.get("risk_score", 0.0),
                    "complexity_score": pattern.get("complexity_score", 0.0),
                    "created_at": datetime.utcnow().isoformat(),
                }

                # VectorDBに保存
                content_id = f"{pattern_category}_{hash(pattern['content'])}_{int(datetime.utcnow().timestamp())}"

                await self.vector_storage.store_embedding(
                    content_id=content_id,
                    content=content_for_embedding,
                    embedding=await self.vector_storage.generate_embedding(content_for_embedding),
                    metadata=metadata,
                )

                self._logger.debug(f"Saved pattern: {content_id}")

            except Exception as e:
                self._logger.error(f"Failed to save pattern: {e}")

    def _prepare_content_for_embedding(self, pattern: Dict[str, Any]) -> str:
        """パターンをベクトル化用テキストに変換"""
        content = pattern["content"]
        pattern_type = pattern.get("pattern_type", "UNKNOWN")

        # パターンタイプに応じてコンテキスト情報を追加
        context_parts = [f"Pattern Type: {pattern_type}"]

        if pattern.get("error_level"):
            context_parts.append(f"Error Level: {pattern['error_level']}")

        if pattern.get("frequency"):
            context_parts.append(f"Frequency: {pattern['frequency']}")

        # コンテキスト + 実際のコンテンツ
        return f"{' | '.join(context_parts)}\n\nContent: {content}"

    async def search_similar_patterns(
        self,
        query_text: str,
        pattern_category: Optional[str] = None,
        limit: int = 10,
        threshold: float = 0.7,
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """類似パターン検索"""
        try:
            # フィルター設定
            filters = {}
            if pattern_category:
                filters["pattern_category"] = pattern_category

            # ベクトル検索実行
            results = await self.vector_storage.similarity_search(
                query=query_text, limit=limit, threshold=threshold, filters=filters
            )

            # 詳細情報付きで結果を返す
            detailed_results = []
            for content_id, similarity in results:
                # メタデータ取得（簡易実装）
                metadata = {}  # 実際の実装では、content_idからメタデータを取得
                detailed_results.append((content_id, similarity, metadata))

            return detailed_results

        except Exception as e:
            self._logger.error(f"Failed to search similar patterns: {e}")
            return []

    async def get_pattern_statistics(self) -> Dict[str, Any]:
        """パターン統計情報を取得"""
        try:
            # VectorDB統計
            vector_stats = await self.vector_storage.get_embedding_statistics()

            # SQL統計
            stats_sql = """
            SELECT 
                COUNT(*) as total_logs,
                COUNT(DISTINCT terminal_id) as active_terminals,
                COUNT(CASE WHEN error_level = 'ERROR' THEN 1 END) as error_count,
                COUNT(CASE WHEN log_type = 'COMMAND' THEN 1 END) as command_count
            FROM terminal_logs 
            WHERE timestamp > datetime('now', '-24 hours')
            """

            sql_stats = await self.sql_storage.fetch_one(stats_sql, [])

            return {
                "vector_storage": vector_stats,
                "sql_storage": sql_stats,
                "extraction_config": self.pattern_config,
                "generated_at": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            self._logger.error(f"Failed to get pattern statistics: {e}")
            return {}

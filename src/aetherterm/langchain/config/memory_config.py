"""メモリ管理設定クラス"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict

logger = logging.getLogger(__name__)


class MemoryStrategy(Enum):
    """メモリ戦略"""

    SHORT_TERM = "short_term"  # 短期メモリのみ
    STRUCTURED = "structured"  # 構造化データのみ
    SEMANTIC = "semantic"  # セマンティック検索のみ
    HYBRID = "hybrid"  # ハイブリッド検索


@dataclass
class MemoryConfig:
    """メモリ管理設定"""

    # 階層化メモリ設定
    short_term_ttl_seconds: int = 3600  # 短期メモリ保持時間（1時間）
    medium_term_days: int = 30  # 中期メモリ保持日数
    long_term_days: int = 365  # 長期メモリ保持日数

    # 容量制限
    max_short_term_entries: int = 1000  # 短期メモリ最大エントリ数
    max_medium_term_entries: int = 10000  # 中期メモリ最大エントリ数
    max_long_term_entries: int = 100000  # 長期メモリ最大エントリ数

    # 検索設定
    default_strategy: MemoryStrategy = MemoryStrategy.HYBRID
    similarity_threshold: float = 0.7
    max_search_results: int = 10
    search_timeout_seconds: int = 15

    # 埋め込み設定
    embedding_dimension: int = 1536  # OpenAI embedding dimension
    embedding_batch_size: int = 100
    embedding_cache_enabled: bool = True
    embedding_cache_ttl_seconds: int = 86400  # 24時間

    # クリーンアップ設定
    cleanup_interval_hours: int = 24  # クリーンアップ実行間隔
    cleanup_batch_size: int = 1000  # クリーンアップバッチサイズ
    auto_cleanup_enabled: bool = True

    # パフォーマンス設定
    enable_async_operations: bool = True
    max_concurrent_operations: int = 10
    operation_timeout_seconds: int = 30

    def validate(self) -> None:
        """設定値の検証"""
        errors = []

        # 時間・日数の検証
        if self.short_term_ttl_seconds <= 0:
            errors.append("short_term_ttl_secondsは正の値である必要があります")

        if self.medium_term_days <= 0:
            errors.append("medium_term_daysは正の値である必要があります")

        if self.long_term_days <= 0:
            errors.append("long_term_daysは正の値である必要があります")

        # 容量制限の検証
        if self.max_short_term_entries <= 0:
            errors.append("max_short_term_entriesは正の値である必要があります")

        if self.max_medium_term_entries <= 0:
            errors.append("max_medium_term_entriesは正の値である必要があります")

        if self.max_long_term_entries <= 0:
            errors.append("max_long_term_entriesは正の値である必要があります")

        # 検索設定の検証
        if not 0.0 <= self.similarity_threshold <= 1.0:
            errors.append("similarity_thresholdは0.0から1.0の範囲である必要があります")

        if self.max_search_results <= 0:
            errors.append("max_search_resultsは正の値である必要があります")

        if self.search_timeout_seconds <= 0:
            errors.append("search_timeout_secondsは正の値である必要があります")

        # 埋め込み設定の検証
        if self.embedding_dimension <= 0:
            errors.append("embedding_dimensionは正の値である必要があります")

        if self.embedding_batch_size <= 0:
            errors.append("embedding_batch_sizeは正の値である必要があります")

        # パフォーマンス設定の検証
        if self.max_concurrent_operations <= 0:
            errors.append("max_concurrent_operationsは正の値である必要があります")

        if self.operation_timeout_seconds <= 0:
            errors.append("operation_timeout_secondsは正の値である必要があります")

        if errors:
            error_message = "メモリ設定検証エラー:\n" + "\n".join(f"- {error}" for error in errors)
            logger.error(error_message)
            raise ValueError(error_message)

        logger.info("メモリ設定の検証が完了しました")

    def get_strategy_weights(self, strategy: MemoryStrategy) -> Dict[str, float]:
        """戦略に基づく重み配分を取得"""
        weight_matrix = {
            MemoryStrategy.SHORT_TERM: {"short_term": 1.0, "structured": 0.0, "semantic": 0.0},
            MemoryStrategy.STRUCTURED: {"short_term": 0.1, "structured": 0.9, "semantic": 0.0},
            MemoryStrategy.SEMANTIC: {"short_term": 0.1, "structured": 0.0, "semantic": 0.9},
            MemoryStrategy.HYBRID: {"short_term": 0.3, "structured": 0.3, "semantic": 0.4},
        }

        return weight_matrix.get(strategy, weight_matrix[MemoryStrategy.HYBRID])

    def calculate_retention_cutoff_days(self, memory_type: str) -> int:
        """メモリタイプに基づく保持期間を計算"""
        retention_map = {
            "short_term": 1,  # 1日
            "medium_term": self.medium_term_days,
            "long_term": self.long_term_days,
        }

        return retention_map.get(memory_type, self.medium_term_days)

    def get_max_entries(self, memory_type: str) -> int:
        """メモリタイプに基づく最大エントリ数を取得"""
        max_entries_map = {
            "short_term": self.max_short_term_entries,
            "medium_term": self.max_medium_term_entries,
            "long_term": self.max_long_term_entries,
        }

        return max_entries_map.get(memory_type, self.max_medium_term_entries)

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "short_term_ttl_seconds": self.short_term_ttl_seconds,
            "medium_term_days": self.medium_term_days,
            "long_term_days": self.long_term_days,
            "max_short_term_entries": self.max_short_term_entries,
            "max_medium_term_entries": self.max_medium_term_entries,
            "max_long_term_entries": self.max_long_term_entries,
            "default_strategy": self.default_strategy.value,
            "similarity_threshold": self.similarity_threshold,
            "max_search_results": self.max_search_results,
            "search_timeout_seconds": self.search_timeout_seconds,
            "embedding_dimension": self.embedding_dimension,
            "embedding_batch_size": self.embedding_batch_size,
            "embedding_cache_enabled": self.embedding_cache_enabled,
            "embedding_cache_ttl_seconds": self.embedding_cache_ttl_seconds,
            "cleanup_interval_hours": self.cleanup_interval_hours,
            "cleanup_batch_size": self.cleanup_batch_size,
            "auto_cleanup_enabled": self.auto_cleanup_enabled,
            "enable_async_operations": self.enable_async_operations,
            "max_concurrent_operations": self.max_concurrent_operations,
            "operation_timeout_seconds": self.operation_timeout_seconds,
        }

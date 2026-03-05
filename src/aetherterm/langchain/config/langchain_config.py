"""LangChain統合設定管理クラス"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class LangChainConfig:
    """LangChain統合設定"""

    # 基本設定
    enabled: bool = True
    debug: bool = False
    log_level: str = "INFO"
    environment: str = "development"

    # メモリ設定
    retention_days: int = 30
    max_conversations_per_session: int = 100
    vector_store_type: str = "chroma"  # chroma, faiss, pinecone

    # データベース設定
    sql_database_url: Optional[str] = None
    redis_url: Optional[str] = None
    vector_store_path: str = "./data/vector_store"

    # 要約設定
    realtime_interval_minutes: int = 5
    max_log_entries_per_summary: int = 1000
    summarization_model: str = "gpt-3.5-turbo"
    summary_max_tokens: int = 500
    batch_processing_enabled: bool = True
    batch_size: int = 100

    # 検索設定
    similarity_threshold: float = 0.7
    max_context_entries: int = 5
    embedding_model: str = "text-embedding-ada-002"
    search_timeout_seconds: int = 10
    enable_hybrid_search: bool = True
    cache_search_results: bool = True

    # AIプロバイダー設定
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    default_provider: str = "openai"
    fallback_provider: str = "anthropic"
    rate_limit_requests_per_minute: int = 100

    # セキュリティ設定
    encryption_enabled: bool = True
    encryption_key: Optional[str] = None
    access_control_enabled: bool = True
    audit_logging_enabled: bool = True
    data_retention_policy: str = "encrypt_and_archive"

    # パフォーマンス設定
    max_concurrent_tasks: int = 20
    connection_pool_size: int = 50
    cache_ttl_seconds: int = 7200
    enable_compression: bool = True

    # 監視設定
    metrics_enabled: bool = True
    health_check_interval_seconds: int = 30
    alert_thresholds: Dict[str, float] = None

    def __post_init__(self):
        """初期化後の処理"""
        if self.alert_thresholds is None:
            self.alert_thresholds = {
                "error_rate": 0.02,
                "response_time_p95": 1.5,
                "memory_usage": 0.85,
                "cpu_usage": 0.80,
            }

    @classmethod
    def from_env(cls) -> "LangChainConfig":
        """環境変数から設定を読み込み"""
        try:
            config = cls(
                enabled=os.getenv("LANGCHAIN_ENABLED", "true").lower() == "true",
                debug=os.getenv("LANGCHAIN_DEBUG", "false").lower() == "true",
                log_level=os.getenv("LANGCHAIN_LOG_LEVEL", "INFO"),
                environment=os.getenv("LANGCHAIN_ENVIRONMENT", "development"),
                retention_days=int(os.getenv("LANGCHAIN_RETENTION_DAYS", "30")),
                max_conversations_per_session=int(os.getenv("LANGCHAIN_MAX_CONVERSATIONS", "100")),
                vector_store_type=os.getenv("LANGCHAIN_VECTOR_STORE_TYPE", "chroma"),
                sql_database_url=os.getenv("DATABASE_URL"),
                redis_url=os.getenv("REDIS_URL"),
                vector_store_path=os.getenv("LANGCHAIN_VECTOR_STORE_PATH", "./data/vector_store"),
                realtime_interval_minutes=int(os.getenv("LANGCHAIN_REALTIME_INTERVAL", "5")),
                max_log_entries_per_summary=int(os.getenv("LANGCHAIN_MAX_LOG_ENTRIES", "1000")),
                summarization_model=os.getenv("LANGCHAIN_SUMMARIZATION_MODEL", "gpt-3.5-turbo"),
                summary_max_tokens=int(os.getenv("LANGCHAIN_SUMMARY_MAX_TOKENS", "500")),
                batch_processing_enabled=os.getenv("LANGCHAIN_BATCH_PROCESSING", "true").lower()
                == "true",
                batch_size=int(os.getenv("LANGCHAIN_BATCH_SIZE", "100")),
                similarity_threshold=float(os.getenv("LANGCHAIN_SIMILARITY_THRESHOLD", "0.7")),
                max_context_entries=int(os.getenv("LANGCHAIN_MAX_CONTEXT_ENTRIES", "5")),
                embedding_model=os.getenv("LANGCHAIN_EMBEDDING_MODEL", "text-embedding-ada-002"),
                search_timeout_seconds=int(os.getenv("LANGCHAIN_SEARCH_TIMEOUT", "10")),
                enable_hybrid_search=os.getenv("LANGCHAIN_HYBRID_SEARCH", "true").lower() == "true",
                cache_search_results=os.getenv("LANGCHAIN_CACHE_SEARCH", "true").lower() == "true",
                openai_api_key=os.getenv("OPENAI_API_KEY"),
                anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
                default_provider=os.getenv("LANGCHAIN_DEFAULT_PROVIDER", "openai"),
                fallback_provider=os.getenv("LANGCHAIN_FALLBACK_PROVIDER", "anthropic"),
                rate_limit_requests_per_minute=int(os.getenv("LANGCHAIN_RATE_LIMIT", "100")),
                encryption_enabled=os.getenv("LANGCHAIN_ENCRYPTION_ENABLED", "true").lower()
                == "true",
                encryption_key=os.getenv("LANGCHAIN_ENCRYPTION_KEY"),
                access_control_enabled=os.getenv("LANGCHAIN_ACCESS_CONTROL", "true").lower()
                == "true",
                audit_logging_enabled=os.getenv("LANGCHAIN_AUDIT_LOGGING", "true").lower()
                == "true",
                data_retention_policy=os.getenv(
                    "LANGCHAIN_DATA_RETENTION_POLICY", "encrypt_and_archive"
                ),
                max_concurrent_tasks=int(os.getenv("LANGCHAIN_MAX_CONCURRENT_TASKS", "20")),
                connection_pool_size=int(os.getenv("LANGCHAIN_CONNECTION_POOL_SIZE", "50")),
                cache_ttl_seconds=int(os.getenv("LANGCHAIN_CACHE_TTL", "7200")),
                enable_compression=os.getenv("LANGCHAIN_COMPRESSION", "true").lower() == "true",
                metrics_enabled=os.getenv("LANGCHAIN_METRICS_ENABLED", "true").lower() == "true",
                health_check_interval_seconds=int(
                    os.getenv("LANGCHAIN_HEALTH_CHECK_INTERVAL", "30")
                ),
            )

            logger.info(
                f"LangChain設定を環境変数から読み込みました (environment: {config.environment})"
            )
            return config

        except Exception as e:
            logger.error(f"環境変数からの設定読み込みに失敗: {e}")
            raise ValueError(f"LangChain設定の読み込みに失敗しました: {e}")

    def validate(self) -> None:
        """設定値の検証"""
        errors = []

        if self.enabled:
            # APIキーの検証
            if not self.openai_api_key and not self.anthropic_api_key:
                errors.append("AIプロバイダーのAPIキーが設定されていません")

            # 数値範囲の検証
            if self.retention_days <= 0:
                errors.append("retention_daysは正の値である必要があります")

            if self.max_conversations_per_session <= 0:
                errors.append("max_conversations_per_sessionは正の値である必要があります")

            if not 0.0 <= self.similarity_threshold <= 1.0:
                errors.append("similarity_thresholdは0.0から1.0の範囲である必要があります")

            if self.max_context_entries <= 0:
                errors.append("max_context_entriesは正の値である必要があります")

            if self.search_timeout_seconds <= 0:
                errors.append("search_timeout_secondsは正の値である必要があります")

            # ベクトルストアタイプの検証
            if self.vector_store_type not in ["chroma", "faiss", "pinecone"]:
                errors.append(f"サポートされていないvector_store_type: {self.vector_store_type}")

            # プロバイダーの検証
            if self.default_provider not in ["openai", "anthropic"]:
                errors.append(f"サポートされていないdefault_provider: {self.default_provider}")

            # パスの検証
            if self.vector_store_path:
                vector_store_dir = Path(self.vector_store_path).parent
                if not vector_store_dir.exists():
                    try:
                        vector_store_dir.mkdir(parents=True, exist_ok=True)
                        logger.info(f"ベクトルストアディレクトリを作成しました: {vector_store_dir}")
                    except Exception as e:
                        errors.append(f"ベクトルストアディレクトリの作成に失敗: {e}")

        if errors:
            error_message = "設定検証エラー:\n" + "\n".join(f"- {error}" for error in errors)
            logger.error(error_message)
            raise ValueError(error_message)

        logger.info("LangChain設定の検証が完了しました")

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換（機密情報を除く）"""
        config_dict = {}
        for key, value in self.__dict__.items():
            # 機密情報は除外
            if "key" in key.lower() or "password" in key.lower():
                config_dict[key] = "***" if value else None
            else:
                config_dict[key] = value
        return config_dict

    def get_database_url(self) -> Optional[str]:
        """データベースURL取得（フォールバック付き）"""
        if self.sql_database_url:
            return self.sql_database_url

        # 開発環境用のデフォルトSQLite URL
        if self.environment == "development":
            return "sqlite:///./data/langchain.db"

        return None

    def get_redis_url(self) -> Optional[str]:
        """Redis URL取得（フォールバック付き）"""
        if self.redis_url:
            return self.redis_url

        # 開発環境用のデフォルトRedis URL
        if self.environment == "development":
            return "redis://localhost:6379/0"

        return None

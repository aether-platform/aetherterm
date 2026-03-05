"""ストレージ設定クラス"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class VectorStoreType(Enum):
    """ベクトルストアタイプ"""

    CHROMA = "chroma"
    FAISS = "faiss"
    PINECONE = "pinecone"
    PGVECTOR = "pgvector"


class DatabaseType(Enum):
    """データベースタイプ"""

    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"


@dataclass
class StorageConfig:
    """ストレージ設定"""

    # ベクトルストア設定
    vector_store_type: VectorStoreType = VectorStoreType.CHROMA
    vector_store_path: str = "./data/vector_store"
    vector_index_type: str = "hnsw"  # hnsw, ivf, flat
    vector_distance_metric: str = "cosine"  # cosine, euclidean, dot_product

    # Chroma設定
    chroma_host: Optional[str] = None
    chroma_port: int = 8000
    chroma_collection_name: str = "aetherterm_conversations"
    chroma_persist_directory: Optional[str] = None

    # FAISS設定
    faiss_index_factory: str = "IVF100,Flat"
    faiss_nprobe: int = 10
    faiss_use_gpu: bool = False

    # Pinecone設定
    pinecone_api_key: Optional[str] = None
    pinecone_environment: str = "us-west1-gcp"
    pinecone_index_name: str = "aetherterm-index"
    pinecone_dimension: int = 1536

    # SQL データベース設定
    database_type: DatabaseType = DatabaseType.SQLITE
    database_url: Optional[str] = None
    database_pool_size: int = 20
    database_max_overflow: int = 30
    database_pool_timeout: int = 30
    database_pool_recycle: int = 3600

    # PostgreSQL設定
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_database: str = "aetherterm"
    postgres_username: Optional[str] = None
    postgres_password: Optional[str] = None
    postgres_ssl_mode: str = "prefer"

    # Redis設定
    redis_url: Optional[str] = None
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_database: int = 0
    redis_password: Optional[str] = None
    redis_ssl: bool = False
    redis_connection_pool_size: int = 50
    redis_socket_timeout: int = 5
    redis_socket_connect_timeout: int = 5

    # キャッシュ設定
    enable_query_cache: bool = True
    query_cache_ttl_seconds: int = 1800  # 30分
    enable_embedding_cache: bool = True
    embedding_cache_ttl_seconds: int = 86400  # 24時間
    cache_compression_enabled: bool = True

    # バックアップ設定
    backup_enabled: bool = True
    backup_interval_hours: int = 24
    backup_retention_days: int = 7
    backup_directory: str = "./data/backups"
    backup_compression: bool = True

    # パフォーマンス設定
    batch_insert_size: int = 1000
    connection_timeout_seconds: int = 30
    query_timeout_seconds: int = 60
    enable_connection_pooling: bool = True

    def validate(self) -> None:
        """設定値の検証"""
        errors = []

        # ベクトルストア設定の検証
        if self.vector_store_type == VectorStoreType.PINECONE:
            if not self.pinecone_api_key:
                errors.append("Pinecone使用時はpinecone_api_keyが必要です")

            if self.pinecone_dimension <= 0:
                errors.append("pinecone_dimensionは正の値である必要があります")

        # データベース設定の検証
        if self.database_type == DatabaseType.POSTGRESQL:
            if not self.postgres_username:
                errors.append("PostgreSQL使用時はpostgres_usernameが必要です")

        # 数値範囲の検証
        if self.database_pool_size <= 0:
            errors.append("database_pool_sizeは正の値である必要があります")

        if self.database_max_overflow < 0:
            errors.append("database_max_overflowは0以上である必要があります")

        if self.redis_port <= 0 or self.redis_port > 65535:
            errors.append("redis_portは1-65535の範囲である必要があります")

        if self.redis_database < 0:
            errors.append("redis_databaseは0以上である必要があります")

        if self.batch_insert_size <= 0:
            errors.append("batch_insert_sizeは正の値である必要があります")

        if self.connection_timeout_seconds <= 0:
            errors.append("connection_timeout_secondsは正の値である必要があります")

        if self.query_timeout_seconds <= 0:
            errors.append("query_timeout_secondsは正の値である必要があります")

        if errors:
            error_message = "ストレージ設定検証エラー:\n" + "\n".join(
                f"- {error}" for error in errors
            )
            logger.error(error_message)
            raise ValueError(error_message)

        logger.info("ストレージ設定の検証が完了しました")

    def get_database_url(self) -> str:
        """データベースURL生成"""
        if self.database_url:
            return self.database_url

        if self.database_type == DatabaseType.SQLITE:
            return "sqlite:///./data/aetherterm.db"

        if self.database_type == DatabaseType.POSTGRESQL:
            password_part = f":{self.postgres_password}" if self.postgres_password else ""
            return (
                f"postgresql://{self.postgres_username}{password_part}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_database}"
            )

        raise ValueError(f"サポートされていないデータベースタイプ: {self.database_type}")

    def get_redis_url(self) -> str:
        """Redis URL生成"""
        if self.redis_url:
            return self.redis_url

        password_part = f":{self.redis_password}@" if self.redis_password else ""
        protocol = "rediss" if self.redis_ssl else "redis"

        return (
            f"{protocol}://{password_part}{self.redis_host}:{self.redis_port}/{self.redis_database}"
        )

    def get_vector_store_config(self) -> Dict[str, Any]:
        """ベクトルストア設定を取得"""
        base_config = {
            "type": self.vector_store_type.value,
            "path": self.vector_store_path,
            "distance_metric": self.vector_distance_metric,
        }

        if self.vector_store_type == VectorStoreType.CHROMA:
            base_config.update(
                {
                    "host": self.chroma_host,
                    "port": self.chroma_port,
                    "collection_name": self.chroma_collection_name,
                    "persist_directory": self.chroma_persist_directory or self.vector_store_path,
                }
            )

        elif self.vector_store_type == VectorStoreType.FAISS:
            base_config.update(
                {
                    "index_factory": self.faiss_index_factory,
                    "nprobe": self.faiss_nprobe,
                    "use_gpu": self.faiss_use_gpu,
                }
            )

        elif self.vector_store_type == VectorStoreType.PINECONE:
            base_config.update(
                {
                    "api_key": self.pinecone_api_key,
                    "environment": self.pinecone_environment,
                    "index_name": self.pinecone_index_name,
                    "dimension": self.pinecone_dimension,
                }
            )

        return base_config

    def get_cache_config(self) -> Dict[str, Any]:
        """キャッシュ設定を取得"""
        return {
            "query_cache": {
                "enabled": self.enable_query_cache,
                "ttl_seconds": self.query_cache_ttl_seconds,
            },
            "embedding_cache": {
                "enabled": self.enable_embedding_cache,
                "ttl_seconds": self.embedding_cache_ttl_seconds,
            },
            "compression_enabled": self.cache_compression_enabled,
        }

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換（機密情報を除く）"""
        config_dict = {}
        for key, value in self.__dict__.items():
            # 機密情報は除外
            if any(secret in key.lower() for secret in ["password", "key", "secret"]):
                config_dict[key] = "***" if value else None
            elif isinstance(value, Enum):
                config_dict[key] = value.value
            else:
                config_dict[key] = value

        return config_dict

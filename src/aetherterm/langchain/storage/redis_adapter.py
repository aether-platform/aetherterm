"""Redisストレージアダプター（短期メモリ用）"""

import json
import logging
import pickle
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
from redis.asyncio import Redis

from ..config.storage_config import StorageConfig
from ..models.conversation import ConversationEntry
from ..models.session import SessionContext
from .base_storage import BaseStorageAdapter, CacheStorageAdapter

logger = logging.getLogger(__name__)


class RedisStorageAdapter(BaseStorageAdapter, CacheStorageAdapter):
    """Redisストレージアダプター"""

    def __init__(self, config: StorageConfig):
        """初期化

        Args:
            config: ストレージ設定
        """
        if redis is None:
            raise ImportError("redis パッケージがインストールされていません")

        super().__init__(config.to_dict())
        self.config = config
        self._redis: Optional[Redis] = None

        # キー接頭辞
        self.key_prefixes = {
            "conversation": "aetherterm:conv:",
            "session": "aetherterm:session:",
            "cache": "aetherterm:cache:",
            "embedding": "aetherterm:embed:",
            "summary": "aetherterm:summary:",
        }

    async def _connect_impl(self) -> None:
        """Redis接続実装"""
        try:
            self._redis = redis.from_url(
                self.config.get_redis_url(),
                socket_timeout=self.config.redis_socket_timeout,
                socket_connect_timeout=self.config.redis_socket_connect_timeout,
                max_connections=self.config.redis_connection_pool_size,
                decode_responses=False,  # バイナリデータ対応
            )

            # 接続テスト
            await self._redis.ping()
            self._logger.info("Redisに接続しました")

        except Exception as e:
            self._logger.error(f"Redis接続エラー: {e}")
            raise

    async def _disconnect_impl(self) -> None:
        """Redis切断実装"""
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def _health_check_impl(self) -> Dict[str, Any]:
        """Redisヘルスチェック実装"""
        if not self._redis:
            raise RuntimeError("Redis接続が確立されていません")

        info = await self._redis.info()
        return {
            "redis_version": info.get("redis_version"),
            "connected_clients": info.get("connected_clients"),
            "used_memory": info.get("used_memory"),
            "used_memory_human": info.get("used_memory_human"),
            "keyspace_hits": info.get("keyspace_hits"),
            "keyspace_misses": info.get("keyspace_misses"),
        }

    def _make_key(self, prefix: str, key: str) -> str:
        """キーを生成"""
        return f"{self.key_prefixes[prefix]}{key}"

    async def cache_recent_conversation(self, entry: ConversationEntry) -> None:
        """最近の会話をキャッシュ

        Args:
            entry: 会話エントリ
        """
        if not self._redis:
            await self.connect()

        try:
            # セッション別の最近の会話リストに追加
            session_key = self._make_key("conversation", f"recent:{entry.session_id}")

            # エントリをシリアライズ
            serialized_entry = pickle.dumps(entry.to_dict())

            # リストの先頭に追加
            await self._redis.lpush(session_key, serialized_entry)

            # リストサイズを制限（最新100件まで）
            await self._redis.ltrim(session_key, 0, 99)

            # TTLを設定（1時間）
            await self._redis.expire(session_key, 3600)

            self._logger.debug(f"会話をキャッシュしました: {entry.id}")

        except Exception as e:
            self._logger.error(f"会話キャッシュエラー: {e}")
            raise

    async def get_recent_conversations(
        self, session_id: str, limit: int = 10
    ) -> List[ConversationEntry]:
        """最近の会話を取得

        Args:
            session_id: セッションID
            limit: 取得件数制限

        Returns:
            List[ConversationEntry]: 最近の会話リスト
        """
        if not self._redis:
            await self.connect()

        try:
            session_key = self._make_key("conversation", f"recent:{session_id}")

            # リストから最新のエントリを取得
            serialized_entries = await self._redis.lrange(session_key, 0, limit - 1)

            conversations = []
            for serialized_entry in serialized_entries:
                try:
                    entry_dict = pickle.loads(serialized_entry)
                    conversation = ConversationEntry.from_dict(entry_dict)
                    conversations.append(conversation)
                except Exception as e:
                    self._logger.warning(f"会話エントリのデシリアライズに失敗: {e}")
                    continue

            self._logger.debug(f"キャッシュから会話を取得: {len(conversations)}件")
            return conversations

        except Exception as e:
            self._logger.error(f"会話取得エラー: {e}")
            return []

    async def cache_session_context(self, context: SessionContext) -> None:
        """セッションコンテキストをキャッシュ

        Args:
            context: セッションコンテキスト
        """
        if not self._redis:
            await self.connect()

        try:
            session_key = self._make_key("session", context.session_id)

            # コンテキストをシリアライズ
            serialized_context = pickle.dumps(context.to_dict())

            # キャッシュに保存（TTL: 2時間）
            await self._redis.setex(session_key, 7200, serialized_context)

            self._logger.debug(f"セッションコンテキストをキャッシュしました: {context.session_id}")

        except Exception as e:
            self._logger.error(f"セッションキャッシュエラー: {e}")
            raise

    async def get_session_context(self, session_id: str) -> Optional[SessionContext]:
        """セッションコンテキストを取得

        Args:
            session_id: セッションID

        Returns:
            Optional[SessionContext]: セッションコンテキスト
        """
        if not self._redis:
            await self.connect()

        try:
            session_key = self._make_key("session", session_id)

            serialized_context = await self._redis.get(session_key)
            if not serialized_context:
                return None

            context_dict = pickle.loads(serialized_context)
            return SessionContext.from_dict(context_dict)

        except Exception as e:
            self._logger.error(f"セッション取得エラー: {e}")
            return None

    async def cleanup_old_cache(self) -> int:
        """古いキャッシュをクリーンアップ

        Returns:
            int: クリーンアップされたキー数
        """
        if not self._redis:
            await self.connect()

        try:
            deleted_count = 0

            # 各プレフィックスのキーをスキャン
            for prefix in self.key_prefixes.values():
                pattern = f"{prefix}*"

                async for key in self._redis.scan_iter(match=pattern, count=100):
                    # TTLをチェック
                    ttl = await self._redis.ttl(key)

                    # TTLが-1（永続）または非常に長い場合は削除対象
                    if ttl == -1 or ttl > 86400:  # 24時間以上
                        await self._redis.delete(key)
                        deleted_count += 1

            self._logger.info(f"古いキャッシュをクリーンアップしました: {deleted_count}件")
            return deleted_count

        except Exception as e:
            self._logger.error(f"キャッシュクリーンアップエラー: {e}")
            return 0

    # CacheStorageAdapter実装

    async def get(self, key: str) -> Optional[Any]:
        """キャッシュから値を取得"""
        if not self._redis:
            await self.connect()

        try:
            cache_key = self._make_key("cache", key)
            value = await self._redis.get(cache_key)

            if value is None:
                return None

            # JSON形式で保存されている場合はJSONとしてデコード
            try:
                return json.loads(value.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                # バイナリデータの場合はpickleでデシリアライズ
                try:
                    return pickle.loads(value)
                except:
                    # 文字列として返す
                    return value.decode("utf-8")

        except Exception as e:
            self._logger.error(f"キャッシュ取得エラー: {e}")
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int = None) -> None:
        """キャッシュに値を設定"""
        if not self._redis:
            await self.connect()

        try:
            cache_key = self._make_key("cache", key)

            # 値をシリアライズ
            if isinstance(value, (dict, list)):
                serialized_value = json.dumps(value, ensure_ascii=False).encode("utf-8")
            elif isinstance(value, str):
                serialized_value = value.encode("utf-8")
            else:
                serialized_value = pickle.dumps(value)

            # TTLが指定されている場合
            if ttl_seconds:
                await self._redis.setex(cache_key, ttl_seconds, serialized_value)
            else:
                await self._redis.set(cache_key, serialized_value)

        except Exception as e:
            self._logger.error(f"キャッシュ設定エラー: {e}")
            raise

    async def delete(self, key: str) -> bool:
        """キャッシュから値を削除"""
        if not self._redis:
            await self.connect()

        try:
            cache_key = self._make_key("cache", key)
            result = await self._redis.delete(cache_key)
            return result > 0

        except Exception as e:
            self._logger.error(f"キャッシュ削除エラー: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """キーが存在するかチェック"""
        if not self._redis:
            await self.connect()

        try:
            cache_key = self._make_key("cache", key)
            result = await self._redis.exists(cache_key)
            return result > 0

        except Exception as e:
            self._logger.error(f"キャッシュ存在チェックエラー: {e}")
            return False

    async def clear_pattern(self, pattern: str) -> int:
        """パターンにマッチするキーを削除"""
        if not self._redis:
            await self.connect()

        try:
            cache_pattern = self._make_key("cache", pattern)
            deleted_count = 0

            async for key in self._redis.scan_iter(match=cache_pattern, count=100):
                await self._redis.delete(key)
                deleted_count += 1

            return deleted_count

        except Exception as e:
            self._logger.error(f"パターン削除エラー: {e}")
            return 0

    async def get_cache_statistics(self) -> Dict[str, Any]:
        """キャッシュ統計情報を取得"""
        if not self._redis:
            await self.connect()

        try:
            info = await self._redis.info()

            # 各プレフィックスのキー数を取得
            key_counts = {}
            for prefix_name, prefix in self.key_prefixes.items():
                count = 0
                async for _ in self._redis.scan_iter(match=f"{prefix}*", count=100):
                    count += 1
                key_counts[prefix_name] = count

            return {
                "total_keys": sum(key_counts.values()),
                "key_counts_by_type": key_counts,
                "memory_usage": info.get("used_memory"),
                "memory_usage_human": info.get("used_memory_human"),
                "hit_rate": self._calculate_hit_rate(info),
                "connected_clients": info.get("connected_clients"),
            }

        except Exception as e:
            self._logger.error(f"統計情報取得エラー: {e}")
            return {}

    def _calculate_hit_rate(self, info: Dict[str, Any]) -> float:
        """キャッシュヒット率を計算"""
        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)

        if hits + misses == 0:
            return 0.0

        return hits / (hits + misses)

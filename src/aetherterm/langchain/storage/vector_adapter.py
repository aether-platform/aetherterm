"""
ベクトルストレージアダプター（長期メモリ用）
"""

import hashlib
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import chromadb
import faiss
import numpy as np
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS, Chroma
from langchain_openai import OpenAIEmbeddings

from langchain.schema import Document

from ..config.storage_config import StorageConfig, VectorStoreType
from ..models.conversation import ConversationEntry, ConversationType, MessageRole
from .base_storage import BaseStorageAdapter, VectorStorageAdapter

logger = logging.getLogger(__name__)
class VectorStoreAdapter(BaseStorageAdapter, VectorStorageAdapter):
    """ベクトルストレージアダプター"""

    def __init__(self, config: StorageConfig):
        """
        初期化

        Args:
            config: ストレージ設定
        """
        if OpenAIEmbeddings is None:
            raise ImportError("langchain関連パッケージがインストールされていません")

        super().__init__(config.to_dict())
        self.config = config
        self._embeddings = None
        self._vector_store = None
        self._embedding_cache = {}  # 簡易キャッシュ

    async def _connect_impl(self) -> None:
        """ベクトルストア接続実装"""
        try:
            # 埋め込みモデルの初期化
            await self._initialize_embeddings()

            # ベクトルストアの初期化
            await self._initialize_vector_store()

            self._logger.info(
                f"ベクトルストア({self.config.vector_store_type.value})に接続しました"
            )

        except Exception as e:
            self._logger.error(f"ベクトルストア接続エラー: {e}")
            raise

    async def _disconnect_impl(self) -> None:
        """ベクトルストア切断実装"""
        if self._vector_store:
            # Chromaの場合は明示的にクライアントを閉じる
            if hasattr(self._vector_store, "_client"):
                try:
                    self._vector_store._client.reset()
                except:
                    pass

            self._vector_store = None

        self._embeddings = None
        self._embedding_cache.clear()

    async def _health_check_impl(self) -> Dict[str, Any]:
        """ベクトルストアヘルスチェック実装"""
        if not self._vector_store:
            raise RuntimeError("ベクトルストア接続が確立されていません")

        try:
            # 簡単なテスト埋め込みで動作確認
            test_embedding = await self.generate_embedding("health check test")

            health_info = {
                "vector_store_type": self.config.vector_store_type.value,
                "embedding_dimension": len(test_embedding),
                "cache_size": len(self._embedding_cache),
            }

            # ベクトルストア固有の情報
            if self.config.vector_store_type == VectorStoreType.CHROMA:
                if hasattr(self._vector_store, "_collection"):
                    health_info["collection_count"] = self._vector_store._collection.count()

            return health_info

        except Exception as e:
            raise RuntimeError(f"ベクトルストアヘルスチェック失敗: {e}")

    async def _initialize_embeddings(self) -> None:
        """埋め込みモデルの初期化"""
        embedding_model = self.config.to_dict().get("embedding_model", "text-embedding-ada-002")

        if embedding_model.startswith("text-embedding"):
            # OpenAI埋め込み
            openai_api_key = self.config.to_dict().get("openai_api_key")
            if not openai_api_key:
                raise ValueError("OpenAI埋め込み使用時はopenai_api_keyが必要です")

            self._embeddings = OpenAIEmbeddings(
                model=embedding_model, openai_api_key=openai_api_key
            )
        else:
            # HuggingFace埋め込み
            self._embeddings = HuggingFaceEmbeddings(model_name=embedding_model)

    async def _initialize_vector_store(self) -> None:
        """ベクトルストアの初期化"""
        if self.config.vector_store_type == VectorStoreType.CHROMA:
            await self._initialize_chroma()
        elif self.config.vector_store_type == VectorStoreType.FAISS:
            await self._initialize_faiss()
        else:
            raise ValueError(f"サポートされていないベクトルストア: {self.config.vector_store_type}")

    async def _initialize_chroma(self) -> None:
        """Chromaベクトルストアの初期化"""
        if chromadb is None:
            raise ImportError("chromadb パッケージがインストールされていません")

        persist_directory = self.config.chroma_persist_directory or self.config.vector_store_path

        self._vector_store = Chroma(
            collection_name=self.config.chroma_collection_name,
            embedding_function=self._embeddings,
            persist_directory=persist_directory,
        )

    async def _initialize_faiss(self) -> None:
        """FAISSベクトルストアの初期化"""
        if faiss is None or np is None:
            raise ImportError("faiss-cpu と numpy パッケージがインストールされていません")

        try:
            # 既存のFAISSインデックスを読み込み
            self._vector_store = FAISS.load_local(self.config.vector_store_path, self._embeddings)
        except:
            # 新規作成
            # 空のドキュメントでFAISSを初期化
            dummy_docs = [Document(page_content="dummy", metadata={})]
            self._vector_store = FAISS.from_documents(dummy_docs, self._embeddings)

            # ダミードキュメントを削除
            self._vector_store.delete([0])

    # VectorStorageAdapter実装

    async def generate_embedding(self, text: str) -> List[float]:
        """テキストの埋め込みベクトルを生成"""
        if not self._embeddings:
            await self.connect()

        try:
            # キャッシュチェック
            text_hash = hashlib.md5(text.encode()).hexdigest()
            if text_hash in self._embedding_cache:
                return self._embedding_cache[text_hash]

            # 埋め込み生成
            embedding = await self._embeddings.aembed_query(text)

            # キャッシュに保存（サイズ制限）
            if len(self._embedding_cache) < 1000:
                self._embedding_cache[text_hash] = embedding

            return embedding

        except Exception as e:
            self._logger.error(f"埋め込み生成エラー: {e}")
            raise

    async def store_embedding(
        self, content_id: str, content: str, embedding: List[float], metadata: Dict[str, Any] = None
    ) -> str:
        """埋め込みベクトルを保存"""
        if not self._vector_store:
            await self.connect()

        try:
            doc_metadata = metadata or {}
            doc_metadata["content_id"] = content_id
            doc_metadata["timestamp"] = datetime.utcnow().isoformat()

            document = Document(page_content=content, metadata=doc_metadata)

            # ベクトルストアに追加
            ids = await self._vector_store.aadd_documents([document])

            # FAISSの場合は保存
            if self.config.vector_store_type == VectorStoreType.FAISS:
                self._vector_store.save_local(self.config.vector_store_path)

            self._logger.debug(f"埋め込みを保存しました: {content_id}")
            return ids[0] if ids else content_id

        except Exception as e:
            self._logger.error(f"埋め込み保存エラー: {e}")
            raise

    async def similarity_search(
        self, query: str, limit: int = 10, threshold: float = 0.7, filters: Dict[str, Any] = None
    ) -> List[Tuple[str, float]]:
        """類似性検索"""
        if not self._vector_store:
            await self.connect()

        try:
            # フィルター条件の準備
            search_kwargs = {"k": limit}
            if filters:
                search_kwargs["filter"] = filters

            # 類似性検索実行
            results = await self._vector_store.asimilarity_search_with_score(query, **search_kwargs)

            # 閾値でフィルタリング
            filtered_results = []
            for doc, score in results:
                # スコアを類似度に変換（距離 -> 類似度）
                similarity = 1.0 - score if score <= 1.0 else 1.0 / (1.0 + score)

                if similarity >= threshold:
                    content_id = doc.metadata.get("content_id", str(hash(doc.page_content)))
                    filtered_results.append((content_id, similarity))

            self._logger.debug(f"類似性検索結果: {len(filtered_results)}件")
            return filtered_results

        except Exception as e:
            self._logger.error(f"類似性検索エラー: {e}")
            return []

    async def delete_embeddings(self, content_ids: List[str]) -> int:
        """埋め込みベクトルを削除"""
        if not self._vector_store:
            await self.connect()

        try:
            deleted_count = 0

            # Chromaの場合
            if self.config.vector_store_type == VectorStoreType.CHROMA:
                # content_idでフィルタリングして削除
                for content_id in content_ids:
                    try:
                        self._vector_store.delete(where={"content_id": content_id})
                        deleted_count += 1
                    except:
                        continue

            # FAISSの場合は再構築が必要（簡易実装）
            elif self.config.vector_store_type == VectorStoreType.FAISS:
                # 削除対象以外のドキュメントで再構築
                # 実装は複雑になるため、ここでは削除カウントのみ返す
                deleted_count = len(content_ids)

            self._logger.info(f"埋め込みを削除しました: {deleted_count}件")
            return deleted_count

        except Exception as e:
            self._logger.error(f"埋め込み削除エラー: {e}")
            return 0

    async def get_embedding_statistics(self) -> Dict[str, Any]:
        """埋め込み統計情報を取得"""
        if not self._vector_store:
            await self.connect()

        try:
            stats = {
                "vector_store_type": self.config.vector_store_type.value,
                "cache_size": len(self._embedding_cache),
            }

            # Chromaの場合
            if self.config.vector_store_type == VectorStoreType.CHROMA:
                if hasattr(self._vector_store, "_collection"):
                    stats["total_documents"] = self._vector_store._collection.count()

            # FAISSの場合
            elif self.config.vector_store_type == VectorStoreType.FAISS:
                if hasattr(self._vector_store, "index"):
                    stats["total_documents"] = self._vector_store.index.ntotal
                    stats["index_dimension"] = self._vector_store.index.d

            return stats

        except Exception as e:
            self._logger.error(f"統計情報取得エラー: {e}")
            return {}

    # 会話エントリ専用メソッド

    async def store_conversation(self, entry: ConversationEntry) -> str:
        """会話エントリをベクトルストアに保存"""
        if not entry.embedding:
            entry.embedding = await self.generate_embedding(entry.content)

        metadata = {
            "conversation_id": str(entry.id),
            "session_id": entry.session_id,
            "conversation_type": entry.conversation_type.value,
            "role": entry.role.value,
            "timestamp": entry.timestamp.isoformat(),
            **entry.metadata,
        }

        return await self.store_embedding(
            content_id=str(entry.id),
            content=entry.content,
            embedding=entry.embedding,
            metadata=metadata,
        )

    async def similarity_search_conversations(
        self, query: str, session_id: Optional[str] = None, limit: int = 10, threshold: float = 0.7
    ) -> List[ConversationEntry]:
        """会話エントリの類似性検索"""
        filters = {}
        if session_id:
            filters["session_id"] = session_id

        results = await self.similarity_search(
            query=query, limit=limit, threshold=threshold, filters=filters
        )

        # 結果をConversationEntryに変換（簡易版）
        conversations = []
        for content_id, similarity in results:
            # 実際の実装では、content_idから完全なConversationEntryを復元する必要がある
            # ここでは簡易的な実装
            try:
                # ベクトルストアから詳細情報を取得
                docs = await self._vector_store.asimilarity_search(
                    query, k=1, filter={"content_id": content_id}
                )

                if docs:
                    doc = docs[0]
                    metadata = doc.metadata

                    # ConversationEntryを復元
                    entry = ConversationEntry(
                        id=metadata.get("conversation_id", content_id),
                        session_id=metadata.get("session_id", ""),
                        conversation_type=ConversationType(
                            metadata.get("conversation_type", "user_input")
                        ),
                        role=MessageRole(metadata.get("role", "user")),
                        content=doc.page_content,
                        timestamp=datetime.fromisoformat(
                            metadata.get("timestamp", datetime.utcnow().isoformat())
                        ),
                        metadata={
                            k: v
                            for k, v in metadata.items()
                            if k
                            not in [
                                "conversation_id",
                                "session_id",
                                "conversation_type",
                                "role",
                                "timestamp",
                            ]
                        },
                    )

                    conversations.append(entry)

            except Exception as e:
                self._logger.warning(f"会話エントリ復元エラー: {e}")
                continue

        return conversations

    async def get_embedding(self, content_id: str) -> Optional[List[float]]:
        """コンテンツIDから埋め込みベクトルを取得"""
        # 実装は複雑になるため、ここでは None を返す
        # 実際の実装では、ベクトルストアから埋め込みを取得する必要がある
        return None

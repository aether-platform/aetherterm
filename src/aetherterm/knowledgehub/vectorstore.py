"""VectorStore protocol and backend implementations.

The Protocol defines the contract.  Each backend lives in its own class.
KnowledgeService depends only on the Protocol, never on a concrete backend.

Switch backends via environment variable:
    KNOWLEDGEHUB_VECTOR_BACKEND=chroma   (default)
    KNOWLEDGEHUB_VECTOR_BACKEND=qdrant

Backend-specific configuration:
    ChromaDB:
        KNOWLEDGEHUB_CHROMA_DIR  — persistent storage path
        EMBEDDING_URL            — optional external embedding endpoint
        EMBEDDING_MODEL          — model name for external endpoint
        EMBEDDING_API_KEY        — API key for external endpoint
    Qdrant:
        QDRANT_URL               — Qdrant HTTP URL
        EMBEDDING_URL            — required (Qdrant needs external embeddings)
        EMBEDDING_MODEL          — model name
        EMBEDDING_DIM            — vector dimension (default: 384)
        EMBEDDING_API_KEY        — API key
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Protocol, runtime_checkable

log = logging.getLogger("knowledgehub.vectorstore")


# ---------------------------------------------------------------------------
# Protocol (interface)
# ---------------------------------------------------------------------------


@runtime_checkable
class VectorStore(Protocol):
    """Backend-agnostic vector store interface for tenant knowledge."""

    def upsert(
        self,
        tenant_id: str,
        chunks: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None: ...

    def search(
        self,
        tenant_id: str,
        query: str,
        limit: int = 10,
        document_id: str = "",
    ) -> list[dict]: ...

    def delete_by_document(self, tenant_id: str, document_id: str) -> None: ...

    def delete_collection(self, tenant_id: str) -> None: ...


# ---------------------------------------------------------------------------
# ChromaDB backend (default)
# ---------------------------------------------------------------------------


class ChromaVectorStore:
    """ChromaDB-backed vector store.

    Embedding is handled internally by ChromaDB (default: all-MiniLM-L6-v2).
    No external embedding server required.
    """

    def __init__(
        self,
        persist_dir: str,
        embedding_url: str = "",
        embedding_model: str = "",
        embedding_api_key: str = "",
    ) -> None:
        self._persist_dir = persist_dir
        self._client: Any = None
        self._embedding_fn = self._make_embedding_function(
            embedding_url, embedding_model, embedding_api_key
        )

    @staticmethod
    def _make_embedding_function(
        embedding_url: str, embedding_model: str, embedding_api_key: str
    ) -> Any:
        if embedding_url:
            from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

            return OpenAIEmbeddingFunction(
                api_base=embedding_url,
                api_key=embedding_api_key or "dummy",
                model_name=embedding_model or "bge-small-en-v1.5",
            )
        return None

    def _get_client(self) -> Any:
        if self._client is None:
            import chromadb

            self._client = chromadb.PersistentClient(path=self._persist_dir)
            log.info("ChromaDB initialized at %s", self._persist_dir)
        return self._client

    @staticmethod
    def _collection_name(tenant_id: str) -> str:
        return f"knowledge-{tenant_id}"

    def _get_or_create_collection(self, tenant_id: str) -> Any:
        client = self._get_client()
        kwargs: dict[str, Any] = {"name": self._collection_name(tenant_id)}
        if self._embedding_fn is not None:
            kwargs["embedding_function"] = self._embedding_fn
        return client.get_or_create_collection(**kwargs)

    def upsert(
        self,
        tenant_id: str,
        chunks: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        collection = self._get_or_create_collection(tenant_id)

        ids = []
        for i, (chunk, meta) in enumerate(zip(chunks, metadatas)):
            doc_id = meta.get("document_id", "")
            point_id = hashlib.md5(
                f"{tenant_id}:{doc_id}:{i}:{chunk[:100]}".encode()
            ).hexdigest()
            ids.append(point_id)

        collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)
        log.info("Upserted %d chunks to %s", len(chunks), collection.name)

    def search(
        self,
        tenant_id: str,
        query: str,
        limit: int = 10,
        document_id: str = "",
    ) -> list[dict]:
        client = self._get_client()
        name = self._collection_name(tenant_id)

        try:
            collection = client.get_collection(
                name=name, embedding_function=self._embedding_fn
            )
        except Exception:
            return []

        where = {"document_id": document_id} if document_id else None
        results = collection.query(query_texts=[query], n_results=limit, where=where)

        hits: list[dict] = []
        if results and results["documents"]:
            docs = results["documents"][0]
            metas = results["metadatas"][0] if results["metadatas"] else [{}] * len(docs)
            distances = results["distances"][0] if results["distances"] else [0.0] * len(docs)

            for doc, meta, dist in zip(docs, metas, distances):
                score = 1.0 - dist if dist <= 1.0 else 1.0 / (1.0 + dist)
                hits.append({
                    "score": round(score, 4),
                    "chunk": doc,
                    "document_id": meta.get("document_id", ""),
                    "filename": meta.get("filename", ""),
                    "chunk_index": meta.get("chunk_index", 0),
                })

        return hits

    def delete_by_document(self, tenant_id: str, document_id: str) -> None:
        client = self._get_client()
        name = self._collection_name(tenant_id)
        try:
            collection = client.get_collection(
                name=name, embedding_function=self._embedding_fn
            )
        except Exception:
            return
        collection.delete(where={"document_id": document_id})
        log.info("Deleted document %s from %s", document_id, name)

    def delete_collection(self, tenant_id: str) -> None:
        client = self._get_client()
        name = self._collection_name(tenant_id)
        try:
            client.delete_collection(name)
            log.info("Deleted collection: %s", name)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Qdrant backend
# ---------------------------------------------------------------------------


class QdrantVectorStore:
    """Qdrant-backed vector store.

    Requires an external embedding endpoint (EMBEDDING_URL).
    """

    def __init__(
        self,
        url: str = "http://localhost:6333",
        embedding_url: str = "http://localhost:9000/v3",
        embedding_model: str = "bge-small-en-v1.5",
        embedding_dim: int = 384,
        embedding_api_key: str = "",
    ) -> None:
        self._url = url
        self._embedding_url = embedding_url
        self._embedding_model = embedding_model
        self._embedding_dim = embedding_dim
        self._embedding_api_key = embedding_api_key
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from qdrant_client import QdrantClient

            self._client = QdrantClient(url=self._url)
            log.info("Qdrant client connected to %s", self._url)
        return self._client

    @staticmethod
    def _collection_name(tenant_id: str) -> str:
        return f"knowledge-{tenant_id}"

    def _ensure_collection(self, tenant_id: str) -> None:
        from qdrant_client.models import Distance, VectorParams

        client = self._get_client()
        name = self._collection_name(tenant_id)
        if not client.collection_exists(name):
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=self._embedding_dim, distance=Distance.COSINE
                ),
            )
            log.info("Created Qdrant collection: %s", name)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """Synchronous embedding via OpenAI-compatible endpoint."""
        import httpx

        if not texts:
            return []
        url = f"{self._embedding_url.rstrip('/')}/embeddings"
        payload = {"model": self._embedding_model, "input": texts}
        headers: dict[str, str] = {}
        if self._embedding_api_key:
            headers["Authorization"] = f"Bearer {self._embedding_api_key}"

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return [item["embedding"] for item in data["data"]]

    def upsert(
        self,
        tenant_id: str,
        chunks: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        from qdrant_client.models import PointStruct

        client = self._get_client()
        name = self._collection_name(tenant_id)
        self._ensure_collection(tenant_id)

        vectors = self._embed(chunks)

        points = []
        for i, (vec, chunk, meta) in enumerate(zip(vectors, chunks, metadatas)):
            doc_id = meta.get("document_id", "")
            point_id = hashlib.md5(
                f"{tenant_id}:{doc_id}:{i}:{chunk[:100]}".encode()
            ).hexdigest()
            payload = {**meta, "chunk": chunk}
            points.append(PointStruct(id=point_id, vector=vec, payload=payload))

        client.upsert(collection_name=name, points=points)
        log.info("Upserted %d vectors to %s", len(points), name)

    def search(
        self,
        tenant_id: str,
        query: str,
        limit: int = 10,
        document_id: str = "",
    ) -> list[dict]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        client = self._get_client()
        name = self._collection_name(tenant_id)

        if not client.collection_exists(name):
            return []

        query_vector = self._embed([query])[0]

        query_filter = None
        if document_id:
            query_filter = Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
            )

        results = client.query_points(
            collection_name=name,
            query=query_vector,
            limit=limit,
            query_filter=query_filter,
        )

        return [
            {
                "score": round(hit.score, 4),
                "chunk": hit.payload.get("chunk", ""),
                "document_id": hit.payload.get("document_id", ""),
                "filename": hit.payload.get("filename", ""),
                "chunk_index": hit.payload.get("chunk_index", 0),
            }
            for hit in results.points
        ]

    def delete_by_document(self, tenant_id: str, document_id: str) -> None:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        client = self._get_client()
        name = self._collection_name(tenant_id)
        if not client.collection_exists(name):
            return
        client.delete(
            collection_name=name,
            points_selector=Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
            ),
        )
        log.info("Deleted document %s from %s", document_id, name)

    def delete_collection(self, tenant_id: str) -> None:
        client = self._get_client()
        name = self._collection_name(tenant_id)
        if client.collection_exists(name):
            client.delete_collection(name)
            log.info("Deleted collection: %s", name)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_vector_store(
    backend: str = "chroma",
    **kwargs: Any,
) -> VectorStore:
    """Create a VectorStore instance based on backend name.

    Args:
        backend: "chroma" or "qdrant"
        **kwargs: Backend-specific configuration
    """
    if backend == "chroma":
        return ChromaVectorStore(
            persist_dir=kwargs.get("persist_dir", "/var/lib/knowledgehub/chroma"),
            embedding_url=kwargs.get("embedding_url", ""),
            embedding_model=kwargs.get("embedding_model", ""),
            embedding_api_key=kwargs.get("embedding_api_key", ""),
        )
    elif backend == "qdrant":
        return QdrantVectorStore(
            url=kwargs.get("qdrant_url", "http://localhost:6333"),
            embedding_url=kwargs.get("embedding_url", "http://localhost:9000/v3"),
            embedding_model=kwargs.get("embedding_model", "bge-small-en-v1.5"),
            embedding_dim=int(kwargs.get("embedding_dim", 384)),
            embedding_api_key=kwargs.get("embedding_api_key", ""),
        )
    else:
        raise ValueError(f"Unknown vector backend: {backend!r} (supported: chroma, qdrant)")

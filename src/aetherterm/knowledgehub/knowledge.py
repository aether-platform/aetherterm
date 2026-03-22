"""Knowledge RAG service — docling + DocumentStorage + VectorStore.

Manages the full document lifecycle:
  1. Save original file (DocumentStorage)
  2. Parse via docling → Markdown
  3. Chunk → store in VectorStore for semantic retrieval
  4. Delete / purge cleans both storage and vectors

Both backends are pluggable via Protocols (see docstorage.py, vectorstore.py).
"""

from __future__ import annotations

import logging
import os

from aetherterm.knowledgehub.docstorage import DocumentMeta, DocumentStorage
from aetherterm.knowledgehub.vectorstore import VectorStore

log = logging.getLogger("knowledgehub.knowledge")

CHUNK_SIZE = 512
CHUNK_OVERLAP = 64


# ---------------------------------------------------------------------------
# Document parsing (docling)
# ---------------------------------------------------------------------------


def parse_document(file_path: str) -> str:
    """Parse a document file into Markdown using docling.

    Supports: PDF, DOCX, PPTX, XLSX, HTML, images.
    Falls back to raw text read for unsupported formats or if docling is not
    installed.
    """
    try:
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        result = converter.convert(file_path)
        md = result.document.export_to_markdown()
        log.info("Docling parsed %s (%d chars)", file_path, len(md))
        return md
    except ImportError:
        log.warning("docling not installed — reading as raw text")
        return _read_raw(file_path)
    except Exception as e:
        log.warning("Docling failed for %s: %s — falling back to raw text", file_path, e)
        return _read_raw(file_path)


def _read_raw(file_path: str) -> str:
    try:
        with open(file_path, "r", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Split text into overlapping chunks for embedding."""
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start += chunk_size - overlap
    return chunks


# ---------------------------------------------------------------------------
# High-level KnowledgeService
# ---------------------------------------------------------------------------


class KnowledgeService:
    """Manages the full document lifecycle: store, vectorize, search, delete, purge.

    Usage:
        from aetherterm.knowledgehub.vectorstore import create_vector_store
        from aetherterm.knowledgehub.docstorage import LocalDocumentStorage

        docs = LocalDocumentStorage("/data/docs")
        vecs = create_vector_store("chroma", persist_dir="/data/chroma")
        ks = KnowledgeService(docs, vecs)

        meta = await ks.ingest("t1", "doc1", "manual.pdf", content)
        results = await ks.search("t1", "authentication flow")
        ks.delete_document("t1", "doc1")   # removes file + vectors
        ks.purge_tenant("t1")              # removes everything
    """

    def __init__(self, documents: DocumentStorage, vectors: VectorStore) -> None:
        self.documents = documents
        self.vectors = vectors

    # ---- ingest ----

    async def ingest(
        self,
        tenant_id: str,
        document_id: str,
        filename: str,
        content: bytes,
        content_type: str = "",
        tags: list[str] | None = None,
    ) -> DocumentMeta:
        """Full ingest pipeline: save file → parse → chunk → vectorize.

        Returns the document metadata (including chunk_count).
        """
        # 1. Save original file
        meta = self.documents.save(
            tenant_id=tenant_id,
            document_id=document_id,
            filename=filename,
            content=content,
            content_type=content_type,
            tags=tags,
        )

        # 2. Parse document to text
        file_path = self.documents.get_file_path(tenant_id, document_id)
        if file_path is None:
            return meta

        text = parse_document(file_path)
        if not text:
            return meta

        # 3. Chunk
        chunks = chunk_text(text)
        if not chunks:
            return meta

        # 4. Delete old vectors (for re-ingest)
        self.vectors.delete_by_document(tenant_id, document_id)

        # 5. Store new vectors
        metadatas = [
            {
                "document_id": document_id,
                "filename": filename,
                "tenant_id": tenant_id,
                "chunk_index": i,
            }
            for i in range(len(chunks))
        ]
        self.vectors.upsert(tenant_id, chunks, metadatas)

        # 6. Update chunk_count in metadata
        self.documents.update_metadata(tenant_id, document_id, chunk_count=len(chunks))
        meta.chunk_count = len(chunks)

        log.info("Ingested %s/%s: %d chunks", tenant_id, document_id, len(chunks))
        return meta

    # ---- search ----

    async def search(
        self,
        tenant_id: str,
        query: str,
        limit: int = 10,
        document_id: str = "",
    ) -> list[dict]:
        """Semantic search across tenant knowledge."""
        return self.vectors.search(tenant_id, query, limit=limit, document_id=document_id)

    async def search_with_platform(
        self,
        tenant_id: str,
        query: str,
        limit: int = 10,
    ) -> list[dict]:
        """Search tenant knowledge + platform knowledge, merged by score."""
        from aetherterm.knowledgehub.storage import PLATFORM_TENANT

        tenant_results = self.vectors.search(tenant_id, query, limit=limit)
        platform_results = self.vectors.search(PLATFORM_TENANT, query, limit=limit)

        merged = tenant_results + platform_results
        merged.sort(key=lambda r: r["score"], reverse=True)
        return merged[:limit]

    async def build_context(
        self,
        tenant_id: str,
        query: str,
        limit: int = 5,
    ) -> str:
        """Search and format results as context text for CLAUDE.md injection."""
        results = await self.search_with_platform(tenant_id, query, limit=limit)
        if not results:
            return ""

        lines = ["## Relevant Knowledge\n"]
        for i, r in enumerate(results, 1):
            source = r.get("filename", "unknown")
            chunk = r.get("chunk", "")
            lines.append(f"### [{i}] {source}\n")
            lines.append(chunk)
            lines.append("")

        return "\n".join(lines)

    # ---- document management ----

    def get_document(self, tenant_id: str, document_id: str) -> DocumentMeta | None:
        return self.documents.get_metadata(tenant_id, document_id)

    def list_documents(self, tenant_id: str) -> list[DocumentMeta]:
        return self.documents.list_documents(tenant_id)

    def download_document(self, tenant_id: str, document_id: str) -> bytes | None:
        return self.documents.load(tenant_id, document_id)

    async def delete_document(self, tenant_id: str, document_id: str) -> bool:
        """Delete document file, then rebuild vectors from remaining documents."""
        ok = self.documents.delete(tenant_id, document_id)
        if ok:
            await self.rebuild_vectors(tenant_id)
        return ok

    def purge_tenant(self, tenant_id: str) -> int:
        """Delete ALL documents + vectors for a tenant.  Returns doc count."""
        self.vectors.delete_collection(tenant_id)
        return self.documents.purge_tenant(tenant_id)

    # ---- rebuild ----

    async def rebuild_vectors(self, tenant_id: str) -> dict[str, int]:
        """Drop and rebuild all vectors from stored documents.

        Use this to repair vector/file inconsistencies, or after changing
        the embedding model or chunk parameters.

        Returns {"documents": N, "chunks": M}.
        """
        self.vectors.delete_collection(tenant_id)

        docs = self.documents.list_documents(tenant_id)
        total_chunks = 0

        for doc in docs:
            file_path = self.documents.get_file_path(tenant_id, doc.document_id)
            if file_path is None:
                log.warning("No file for %s/%s — skipping", tenant_id, doc.document_id)
                continue

            text = parse_document(file_path)
            if not text:
                continue

            chunks = chunk_text(text)
            if not chunks:
                continue

            metadatas = [
                {
                    "document_id": doc.document_id,
                    "filename": doc.filename,
                    "tenant_id": tenant_id,
                    "chunk_index": i,
                }
                for i in range(len(chunks))
            ]
            self.vectors.upsert(tenant_id, chunks, metadatas)

            self.documents.update_metadata(
                tenant_id, doc.document_id, chunk_count=len(chunks)
            )
            total_chunks += len(chunks)

        log.info(
            "Rebuilt vectors for tenant %s: %d docs, %d chunks",
            tenant_id, len(docs), total_chunks,
        )
        return {"documents": len(docs), "chunks": total_chunks}

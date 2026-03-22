"""DocumentStorage — protocol + local filesystem implementation.

Manages the lifecycle of uploaded documents: save, load, delete, list, purge.
The VectorStore handles search; this handles the original files and metadata.

Phase 1: LocalDocumentStorage (filesystem)
Phase 2: S3DocumentStorage (boto3 / MinIO)
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

log = logging.getLogger("knowledgehub.docstorage")


# ---------------------------------------------------------------------------
# Document metadata model
# ---------------------------------------------------------------------------


class DocumentMeta(BaseModel):
    """Persisted metadata for an uploaded document."""

    document_id: str
    tenant_id: str
    filename: str
    content_type: str = ""
    size_bytes: int = 0
    chunk_count: int = 0
    version: int = 1
    tags: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class DocumentStorage(Protocol):
    """Backend-agnostic document storage interface."""

    def save(
        self,
        tenant_id: str,
        document_id: str,
        filename: str,
        content: bytes,
        content_type: str = "",
        tags: list[str] | None = None,
    ) -> DocumentMeta: ...

    def load(self, tenant_id: str, document_id: str) -> bytes | None: ...

    def get_metadata(self, tenant_id: str, document_id: str) -> DocumentMeta | None: ...

    def update_metadata(self, tenant_id: str, document_id: str, **kwargs: Any) -> DocumentMeta | None: ...

    def delete(self, tenant_id: str, document_id: str) -> bool: ...

    def list_documents(self, tenant_id: str) -> list[DocumentMeta]: ...

    def purge_tenant(self, tenant_id: str) -> int: ...

    def get_file_path(self, tenant_id: str, document_id: str) -> str | None: ...


# ---------------------------------------------------------------------------
# Local filesystem implementation
# ---------------------------------------------------------------------------


class LocalDocumentStorage:
    """File-system backed document storage.

    Layout:
        {base_dir}/
        └── {tenant_id}/
            └── {document_id}/
                ├── metadata.json
                └── original{.ext}
    """

    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    def _doc_dir(self, tenant_id: str, document_id: str) -> Path:
        return self._base / tenant_id / document_id

    def _meta_path(self, tenant_id: str, document_id: str) -> Path:
        return self._doc_dir(tenant_id, document_id) / "metadata.json"

    def _find_original(self, tenant_id: str, document_id: str) -> Path | None:
        d = self._doc_dir(tenant_id, document_id)
        if not d.is_dir():
            return None
        for f in d.iterdir():
            if f.name.startswith("original"):
                return f
        return None

    def save(
        self,
        tenant_id: str,
        document_id: str,
        filename: str,
        content: bytes,
        content_type: str = "",
        tags: list[str] | None = None,
    ) -> DocumentMeta:
        d = self._doc_dir(tenant_id, document_id)
        d.mkdir(parents=True, exist_ok=True)

        # Determine extension from filename
        ext = Path(filename).suffix or ".bin"
        file_path = d / f"original{ext}"
        file_path.write_bytes(content)

        # Check if updating existing
        existing = self.get_metadata(tenant_id, document_id)
        now = datetime.now(timezone.utc).isoformat()

        if existing:
            meta = existing
            meta.filename = filename
            meta.content_type = content_type
            meta.size_bytes = len(content)
            meta.version += 1
            meta.updated_at = now
            if tags is not None:
                meta.tags = tags
        else:
            meta = DocumentMeta(
                document_id=document_id,
                tenant_id=tenant_id,
                filename=filename,
                content_type=content_type,
                size_bytes=len(content),
                tags=tags or [],
                created_at=now,
                updated_at=now,
            )

        self._meta_path(tenant_id, document_id).write_text(
            json.dumps(meta.model_dump(), indent=2)
        )
        log.info("Saved document %s/%s (%d bytes)", tenant_id, document_id, len(content))
        return meta

    def load(self, tenant_id: str, document_id: str) -> bytes | None:
        f = self._find_original(tenant_id, document_id)
        if f is None:
            return None
        return f.read_bytes()

    def get_metadata(self, tenant_id: str, document_id: str) -> DocumentMeta | None:
        path = self._meta_path(tenant_id, document_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return DocumentMeta(**data)
        except Exception:
            log.warning("Corrupt metadata: %s", path)
            return None

    def update_metadata(
        self, tenant_id: str, document_id: str, **kwargs: Any
    ) -> DocumentMeta | None:
        meta = self.get_metadata(tenant_id, document_id)
        if meta is None:
            return None
        for key, value in kwargs.items():
            if hasattr(meta, key):
                setattr(meta, key, value)
        meta.updated_at = datetime.now(timezone.utc).isoformat()
        self._meta_path(tenant_id, document_id).write_text(
            json.dumps(meta.model_dump(), indent=2)
        )
        return meta

    def delete(self, tenant_id: str, document_id: str) -> bool:
        d = self._doc_dir(tenant_id, document_id)
        if not d.exists():
            return False
        shutil.rmtree(d)
        log.info("Deleted document %s/%s", tenant_id, document_id)
        return True

    def list_documents(self, tenant_id: str) -> list[DocumentMeta]:
        tenant_dir = self._base / tenant_id
        if not tenant_dir.is_dir():
            return []
        result: list[DocumentMeta] = []
        for child in sorted(tenant_dir.iterdir()):
            meta_path = child / "metadata.json"
            if meta_path.exists():
                try:
                    data = json.loads(meta_path.read_text())
                    result.append(DocumentMeta(**data))
                except Exception:
                    log.warning("Skipping corrupt metadata: %s", meta_path)
        return result

    def purge_tenant(self, tenant_id: str) -> int:
        """Delete all documents for a tenant.  Returns count of deleted docs."""
        tenant_dir = self._base / tenant_id
        if not tenant_dir.is_dir():
            return 0
        count = sum(1 for d in tenant_dir.iterdir() if d.is_dir())
        shutil.rmtree(tenant_dir)
        log.info("Purged %d documents for tenant %s", count, tenant_id)
        return count

    def get_file_path(self, tenant_id: str, document_id: str) -> str | None:
        f = self._find_original(tenant_id, document_id)
        return str(f) if f else None

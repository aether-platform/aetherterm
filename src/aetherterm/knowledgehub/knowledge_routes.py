"""REST API routes for Knowledge (document RAG) management."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from aetherterm.agiterm.auth.api_key import APIKeyAuthenticator, Tenant
from aetherterm.knowledgehub.docstorage import DocumentMeta
from aetherterm.knowledgehub.knowledge import KnowledgeService

log = logging.getLogger("knowledgehub.knowledge_routes")

router = APIRouter(prefix="/api/v1", tags=["knowledge"])

api_key_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

_auth: APIKeyAuthenticator | None = None
_knowledge: KnowledgeService | None = None


def init_knowledge_routes(auth: APIKeyAuthenticator, knowledge: KnowledgeService) -> None:
    global _auth, _knowledge
    _auth = auth
    _knowledge = knowledge


def get_tenant(api_key: str = Depends(api_key_header_scheme)) -> Tenant:
    if not _auth or not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    return _auth.authenticate(api_key)


TenantDep = Annotated[Tenant, Depends(get_tenant)]


def _ensure_knowledge() -> KnowledgeService:
    if _knowledge is None:
        raise HTTPException(status_code=503, detail="Knowledge service not available")
    return _knowledge


# --- response models ---


class DocumentResponse(BaseModel):
    document_id: str
    tenant_id: str
    filename: str
    content_type: str = ""
    size_bytes: int = 0
    chunk_count: int = 0
    version: int = 1
    tags: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class SearchRequest(BaseModel):
    query: str
    limit: int = 10
    document_id: str = ""


class SearchResult(BaseModel):
    score: float
    chunk: str
    document_id: str = ""
    filename: str = ""
    chunk_index: int = 0


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]


class ContextRequest(BaseModel):
    query: str
    limit: int = 5


class ContextResponse(BaseModel):
    query: str
    context: str


class PurgeResponse(BaseModel):
    tenant_id: str
    documents_deleted: int


# --- helpers ---


def _meta_to_response(meta: DocumentMeta) -> DocumentResponse:
    return DocumentResponse(**meta.model_dump())


# --- endpoints ---


@router.post("/knowledge/documents", response_model=DocumentResponse, status_code=201)
async def ingest_document(
    tenant: TenantDep,
    file: UploadFile = File(...),
    document_id: str = Form(default=""),
    tags: str = Form(default=""),
):
    """Upload a document for RAG ingestion.

    Saves the original file, parses via docling, chunks, and vectorizes.
    Re-uploading with the same document_id replaces the previous version.
    """
    ks = _ensure_knowledge()

    if not document_id:
        document_id = uuid.uuid4().hex[:12]

    content = await file.read()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    try:
        meta = await ks.ingest(
            tenant_id=tenant.tenant_id,
            document_id=document_id,
            filename=file.filename or "document",
            content=content,
            content_type=file.content_type or "",
            tags=tag_list,
        )
    except Exception as e:
        log.error("Ingestion failed for %s: %s", file.filename, e)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")

    return _meta_to_response(meta)


@router.get("/knowledge/documents", response_model=list[DocumentResponse])
async def list_documents(tenant: TenantDep):
    """List all documents in the tenant's knowledge base."""
    ks = _ensure_knowledge()
    docs = ks.list_documents(tenant.tenant_id)
    return [_meta_to_response(d) for d in docs]


@router.get("/knowledge/documents/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: str, tenant: TenantDep):
    """Get document metadata."""
    ks = _ensure_knowledge()
    meta = ks.get_document(tenant.tenant_id, document_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return _meta_to_response(meta)


@router.get("/knowledge/documents/{document_id}/download")
async def download_document(document_id: str, tenant: TenantDep):
    """Download the original document file."""
    ks = _ensure_knowledge()
    meta = ks.get_document(tenant.tenant_id, document_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Document not found")

    data = ks.download_document(tenant.tenant_id, document_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Document file not found")

    return Response(
        content=data,
        media_type=meta.content_type or "application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={meta.filename}"},
    )


@router.delete("/knowledge/documents/{document_id}")
async def delete_document(document_id: str, tenant: TenantDep):
    """Delete a document (file + vectors)."""
    ks = _ensure_knowledge()
    ok = await ks.delete_document(tenant.tenant_id, document_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "deleted", "document_id": document_id}


@router.delete("/knowledge/purge")
async def purge_tenant(tenant: TenantDep):
    """Delete ALL documents and vectors for the tenant."""
    ks = _ensure_knowledge()
    count = ks.purge_tenant(tenant.tenant_id)
    return PurgeResponse(tenant_id=tenant.tenant_id, documents_deleted=count)


@router.post("/knowledge/rebuild")
async def rebuild_vectors(tenant: TenantDep):
    """Drop and rebuild all vectors from stored documents.

    Use after: embedding model change, chunk parameter tuning,
    or to repair vector/file inconsistencies.
    """
    ks = _ensure_knowledge()
    result = await ks.rebuild_vectors(tenant.tenant_id)
    return {"status": "rebuilt", "tenant_id": tenant.tenant_id, **result}


@router.post("/knowledge/search", response_model=SearchResponse)
async def search_knowledge(req: SearchRequest, tenant: TenantDep):
    """Semantic search across the tenant's knowledge base."""
    ks = _ensure_knowledge()
    results = await ks.search(
        tenant_id=tenant.tenant_id,
        query=req.query,
        limit=req.limit,
        document_id=req.document_id,
    )
    return SearchResponse(query=req.query, results=[SearchResult(**r) for r in results])


@router.post("/knowledge/context", response_model=ContextResponse)
async def build_context(req: ContextRequest, tenant: TenantDep):
    """Search knowledge and return formatted context for CLAUDE.md injection."""
    ks = _ensure_knowledge()
    context = await ks.build_context(
        tenant_id=tenant.tenant_id,
        query=req.query,
        limit=req.limit,
    )
    return ContextResponse(query=req.query, context=context)

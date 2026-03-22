"""REST API routes for SkillRegistry."""

from __future__ import annotations

import io
import json
import logging
import tarfile
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader

from aetherterm.agiterm.auth.api_key import APIKeyAuthenticator, Tenant
from aetherterm.knowledgehub.manager import SkillRegistryManager
from aetherterm.knowledgehub.models import (
    RegisterSkillRequest,
    ResolveRequest,
    ResolveResponse,
    SkillResponse,
    UpdateSkillRequest,
)

log = logging.getLogger("knowledgehub.routes")

router = APIRouter(prefix="/api/v1", tags=["skills"])

api_key_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

_auth: APIKeyAuthenticator | None = None
_manager: SkillRegistryManager | None = None


def init_routes(auth: APIKeyAuthenticator, manager: SkillRegistryManager) -> None:
    global _auth, _manager
    _auth = auth
    _manager = manager


def get_tenant(api_key: str = Depends(api_key_header_scheme)) -> Tenant:
    if not _auth or not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    return _auth.authenticate(api_key)


TenantDep = Annotated[Tenant, Depends(get_tenant)]


# --- helpers ---


def _meta_to_response(meta) -> SkillResponse:
    return SkillResponse(
        skill_id=meta.skill_id,
        tenant_id=meta.tenant_id,
        scope=meta.scope,
        name=meta.name,
        description=meta.description,
        version=meta.version,
        tags=meta.tags,
        context=meta.context,
        env=meta.env,
        created_at=meta.created_at,
        updated_at=meta.updated_at,
    )


# --- endpoints ---


@router.get("/skills", response_model=list[SkillResponse])
async def list_skills(tenant: TenantDep):
    """List all skills visible to the tenant (tenant + platform)."""
    skills = _manager.list_skills(tenant.tenant_id)
    return [_meta_to_response(s) for s in skills]


@router.post("/skills", response_model=SkillResponse, status_code=201)
async def register_skill(
    tenant: TenantDep,
    metadata: str = Form(...),
    files: list[UploadFile] = File(default=[]),
):
    """Register a new skill (multipart: metadata JSON + files)."""
    try:
        req = RegisterSkillRequest.model_validate_json(metadata)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid metadata JSON: {e}")

    file_dict: dict[str, bytes] = {}
    for f in files:
        content = await f.read()
        file_dict[f.filename or "SKILL.md"] = content

    try:
        meta = _manager.register_skill(
            tenant_id=tenant.tenant_id,
            skill_id=req.skill_id,
            name=req.name,
            description=req.description,
            tags=req.tags,
            context=req.context,
            env=req.env,
            files=file_dict,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return _meta_to_response(meta)


@router.get("/skills/{skill_id}", response_model=SkillResponse)
async def get_skill(skill_id: str, tenant: TenantDep):
    """Get skill details (tenant scope first, then platform fallback)."""
    meta = _manager.get_skill(tenant.tenant_id, skill_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return _meta_to_response(meta)


@router.put("/skills/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: str,
    tenant: TenantDep,
    metadata: str = Form(...),
    files: list[UploadFile] = File(default=[]),
):
    """Update a skill (creates a new version)."""
    try:
        update = UpdateSkillRequest.model_validate_json(metadata)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid metadata JSON: {e}")

    file_dict: dict[str, bytes] = {}
    for f in files:
        content = await f.read()
        file_dict[f.filename or "SKILL.md"] = content

    try:
        meta = _manager.update_skill(
            tenant_id=tenant.tenant_id,
            skill_id=skill_id,
            update=update,
            files=file_dict if file_dict else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _meta_to_response(meta)


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str, tenant: TenantDep):
    """Delete a tenant skill."""
    try:
        ok = _manager.delete_skill(tenant.tenant_id, skill_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"status": "deleted", "skill_id": skill_id}


@router.get("/skills/{skill_id}/download")
async def download_skill(skill_id: str, tenant: TenantDep):
    """Download a skill bundle as tar.gz."""
    meta = _manager.get_skill(tenant.tenant_id, skill_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Skill not found")

    from aetherterm.knowledgehub.storage import LocalStorage

    files_dir = _manager._storage.get_skill_files_dir(meta.tenant_id, skill_id)
    if files_dir is None:
        raise HTTPException(status_code=404, detail="Skill files not found")

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path in sorted(files_dir.iterdir()):
            if path.is_file():
                tar.add(str(path), arcname=path.name)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/gzip",
        headers={"Content-Disposition": f"attachment; filename={skill_id}.tar.gz"},
    )


@router.post("/skills/resolve", response_model=ResolveResponse)
async def resolve_skills(req: ResolveRequest, tenant: TenantDep):
    """Resolve skill_ids to injection-ready SkillSource data."""
    resolved, missing = _manager.resolve(tenant.tenant_id, req.skill_ids)
    return ResolveResponse(resolved=resolved, missing=missing)

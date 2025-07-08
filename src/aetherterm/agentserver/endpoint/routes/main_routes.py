"""
Main Routes - Core Application Routes

Provides main application endpoints including index and health checks.
"""

import logging
import os
from typing import Any, Dict

# from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles

from aetherterm.agentserver.infrastructure.config.di_container import MainContainer

# Initialize router
router = APIRouter()
log = logging.getLogger("aetherterm.routes.main")

# Templates - go up from routes to agentserver level
templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "..", "..", "templates")
)

# Mount static files directory - go up from routes to agentserver level
static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "static")
if os.path.exists(static_dir) and os.listdir(static_dir):
    router.mount("/static", StaticFiles(directory=static_dir), name="static")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main index route that serves the terminal interface."""
    # Dynamically find the hashed asset filenames - go up from routes to agentserver level
    assets_dir = os.path.join(os.path.dirname(__file__), "..", "..", "static", "assets")
    js_bundle = ""
    css_bundle = ""
    # Get root path from configuration (use empty string as default)
    root_path = ""

    for filename in os.listdir(assets_dir):
        if filename.startswith("index.") and filename.endswith(".js"):
            js_bundle = f"{root_path}/assets/{filename}"
        elif filename.startswith("index.") and filename.endswith(".css"):
            css_bundle = f"{root_path}/assets/{filename}"

    if not js_bundle or not css_bundle:
        raise HTTPException(status_code=500, detail="Could not find hashed JS or CSS files")

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "js_bundle": js_bundle,
            "css_bundle": css_bundle,
            "favicon_path": f"{root_path}/favicon.ico",
            "uri_root_path": root_path,
        },
    )


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Lightweight health check endpoint for fast response."""
    # Return minimal response for performance
    return {"status": "ok"}


@router.get("/local.js")
async def local_js():
    """Serve local JavaScript files."""
    local_js_dir = os.path.join(os.path.expanduser("~"), ".config", "aetherterm", "local.js")

    js_content = ""
    if os.path.exists(local_js_dir):
        for filename in os.listdir(local_js_dir):
            if not filename.endswith(".js"):
                continue
            file_path = os.path.join(local_js_dir, filename)
            try:
                with open(file_path, encoding="utf-8") as f:
                    js_content += f.read() + ";\n"
            except Exception as e:
                log.warning(f"Could not read {file_path}: {e}")

    return Response(content=js_content, media_type="application/javascript")

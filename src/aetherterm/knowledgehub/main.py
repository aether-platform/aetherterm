"""Entry point for KnowledgeHub service.

Usage:
    aetherterm-knowledgehub --port 8610
    # Or directly:
    python -m aetherterm.knowledgehub.main --port 8610
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import click
import uvicorn

from aetherterm.agiterm.auth.api_key import APIKeyAuthenticator
from aetherterm.knowledgehub.manager import SkillRegistryManager
from aetherterm.knowledgehub.server import create_app
from aetherterm.knowledgehub.storage import LocalStorage

# Built-in platform skills directory (next to this file)
_PLATFORM_SKILLS_DIR = str(Path(__file__).parent / "platform_skills")


@click.command()
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=8610, type=int, help="Bind port")
@click.option("--debug", is_flag=True, help="Debug mode")
@click.option(
    "--storage-dir",
    default=None,
    help="Storage directory (default: /var/lib/knowledgehub)",
)
@click.option(
    "--api-key",
    multiple=True,
    help="Register API key in format tenant_id:name:key (repeatable)",
)
def main(
    host: str,
    port: int,
    debug: bool,
    storage_dir: str | None,
    api_key: tuple[str, ...],
):
    """Start the KnowledgeHub service."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )
    log = logging.getLogger("knowledgehub")

    # Resolve storage directory
    if storage_dir is None:
        storage_dir = os.environ.get("KNOWLEDGEHUB_STORAGE_DIR", "/var/lib/knowledgehub")

    storage = LocalStorage(storage_dir)

    # Bootstrap built-in platform skills
    count = storage.bootstrap_platform_skills(_PLATFORM_SKILLS_DIR)
    if count:
        log.info("Bootstrapped %d platform skills", count)

    manager = SkillRegistryManager(storage)
    auth = APIKeyAuthenticator()

    # Register API keys from CLI args
    for key_spec in api_key:
        parts = key_spec.split(":", 2)
        if len(parts) != 3:
            log.error("Invalid --api-key format: %s (expected tenant_id:name:key)", key_spec)
            continue
        tenant_id, name, key = parts
        auth.register_tenant(tenant_id=tenant_id, name=name, api_key=key)
        log.info("Registered tenant: %s (%s)", tenant_id, name)

    # Also register from environment variable
    env_keys = os.environ.get("KNOWLEDGEHUB_API_KEYS", "")
    for key_spec in env_keys.split(","):
        key_spec = key_spec.strip()
        if not key_spec:
            continue
        parts = key_spec.split(":", 2)
        if len(parts) != 3:
            continue
        tenant_id, name, key = parts
        auth.register_tenant(tenant_id=tenant_id, name=name, api_key=key)

    # Initialize KnowledgeService (RAG) with pluggable backends
    knowledge = None
    backend = os.environ.get("KNOWLEDGEHUB_VECTOR_BACKEND", "chroma")
    try:
        from aetherterm.knowledgehub.docstorage import LocalDocumentStorage
        from aetherterm.knowledgehub.knowledge import KnowledgeService
        from aetherterm.knowledgehub.vectorstore import create_vector_store

        doc_storage = LocalDocumentStorage(os.path.join(storage_dir, "documents"))
        vector_store = create_vector_store(
            backend=backend,
            persist_dir=os.environ.get(
                "KNOWLEDGEHUB_CHROMA_DIR", os.path.join(storage_dir, "chroma")
            ),
            qdrant_url=os.environ.get("QDRANT_URL", "http://localhost:6333"),
            embedding_url=os.environ.get("EMBEDDING_URL", ""),
            embedding_model=os.environ.get("EMBEDDING_MODEL", ""),
            embedding_dim=os.environ.get("EMBEDDING_DIM", "384"),
            embedding_api_key=os.environ.get("EMBEDDING_API_KEY", ""),
        )
        knowledge = KnowledgeService(doc_storage, vector_store)
        log.info("Knowledge RAG enabled (backend: %s)", backend)
    except Exception as e:
        log.warning("Knowledge RAG disabled: %s", e)

    app = create_app(auth=auth, manager=manager, knowledge=knowledge)

    log.info("Starting KnowledgeHub on %s:%d (storage: %s)", host, port, storage_dir)

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="debug" if debug else "info",
    )


if __name__ == "__main__":
    main()

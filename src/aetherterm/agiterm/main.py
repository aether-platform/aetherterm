"""Entry point for WorkWithAGI SDK server.

Usage:
    python -m aetherterm.agiterm.main --port 8600
    # Or via pyproject.toml entry point:
    agiterm-server --port 8600
"""

import logging
import os

import click
import uvicorn

from aetherterm.agiterm.api.server import create_app
from aetherterm.agiterm.auth.api_key import APIKeyAuthenticator
from aetherterm.agiterm.sessions.manager import SDKSessionManager


@click.command()
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=8600, type=int, help="Bind port")
@click.option("--debug", is_flag=True, help="Debug mode")
@click.option(
    "--api-key",
    multiple=True,
    help="Register API key in format tenant_id:name:key (repeatable)",
)
@click.option(
    "--litellm-proxy",
    default="",
    envvar="LITELLM_PROXY_URL",
    help="LiteLLM proxy URL for AI CLI tool API routing (env: LITELLM_PROXY_URL)",
)
def main(host: str, port: int, debug: bool, api_key: tuple[str, ...], litellm_proxy: str):
    """Start the WorkWithAGI SDK server."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )

    log = logging.getLogger("agiterm")

    auth = APIKeyAuthenticator()
    sessions = SDKSessionManager(litellm_proxy_url=litellm_proxy)

    if litellm_proxy:
        log.info("LiteLLM proxy enabled: %s", litellm_proxy)

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
    env_keys = os.environ.get("AGISDK_API_KEYS", "")
    for key_spec in env_keys.split(","):
        key_spec = key_spec.strip()
        if not key_spec:
            continue
        parts = key_spec.split(":", 2)
        if len(parts) != 3:
            continue
        tenant_id, name, key = parts
        auth.register_tenant(tenant_id=tenant_id, name=name, api_key=key)

    app = create_app(auth=auth, sessions=sessions)

    log.info("Starting WorkWithAGI SDK server on %s:%d", host, port)

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="debug" if debug else "info",
    )


if __name__ == "__main__":
    main()

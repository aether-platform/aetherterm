"""API key authentication for WorkWithAGI SDK."""

import hashlib
import hmac
import logging
import time
from dataclasses import dataclass, field

from fastapi import HTTPException, WebSocket, status
from fastapi.security import APIKeyHeader

log = logging.getLogger("agiterm.auth")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass
class Tenant:
    """A tenant (API key holder) with rate limits and metadata."""

    tenant_id: str
    name: str
    api_key_hash: str
    max_sessions: int = 10
    max_concurrent_users: int = 50
    active_sessions: int = 0
    created_at: float = field(default_factory=time.time)
    enabled: bool = True


class APIKeyAuthenticator:
    """Validates API keys and resolves tenants.

    In production this would query a database or cache.
    For now, it uses an in-memory store seeded from config.
    """

    def __init__(self) -> None:
        self._tenants: dict[str, Tenant] = {}  # api_key_hash -> Tenant

    @staticmethod
    def hash_key(api_key: str) -> str:
        return hashlib.sha256(api_key.encode()).hexdigest()

    def register_tenant(
        self,
        tenant_id: str,
        name: str,
        api_key: str,
        max_sessions: int = 10,
        max_concurrent_users: int = 50,
    ) -> Tenant:
        """Register a new tenant with an API key."""
        key_hash = self.hash_key(api_key)
        tenant = Tenant(
            tenant_id=tenant_id,
            name=name,
            api_key_hash=key_hash,
            max_sessions=max_sessions,
            max_concurrent_users=max_concurrent_users,
        )
        self._tenants[key_hash] = tenant
        log.info("Registered tenant %s (%s)", tenant_id, name)
        return tenant

    def authenticate(self, api_key: str) -> Tenant:
        """Authenticate an API key and return the tenant."""
        key_hash = self.hash_key(api_key)
        tenant = self._tenants.get(key_hash)

        if tenant is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )

        if not tenant.enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant is disabled",
            )

        return tenant

    async def authenticate_websocket(self, websocket: WebSocket) -> Tenant:
        """Authenticate a WebSocket connection via query param or header."""
        # Try query parameter first
        api_key = websocket.query_params.get("api_key")

        # Fall back to header
        if not api_key:
            api_key = websocket.headers.get("x-api-key")

        if not api_key:
            await websocket.close(code=4001, reason="Missing API key")
            raise HTTPException(status_code=401, detail="Missing API key")

        try:
            return self.authenticate(api_key)
        except HTTPException:
            await websocket.close(code=4001, reason="Invalid API key")
            raise

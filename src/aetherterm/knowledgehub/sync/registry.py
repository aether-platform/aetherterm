"""In-memory registry for sync connections (CRUD)."""

from __future__ import annotations

import logging
from typing import Any

from aetherterm.knowledgehub.sync.models import SyncConnection, SyncStatus

log = logging.getLogger("knowledgehub.sync.registry")


class SyncConnectionRegistry:
    """Thread-safe in-memory store for :class:`SyncConnection` objects.

    Connections are scoped by *tenant_id* so tenants cannot see each other's
    connections.
    """

    def __init__(self) -> None:
        # {tenant_id: {connection_id: SyncConnection}}
        self._store: dict[str, dict[str, SyncConnection]] = {}

    # ---- queries ----

    def list(self, tenant_id: str) -> list[SyncConnection]:
        """Return all connections for the given tenant."""
        return list(self._store.get(tenant_id, {}).values())

    def get(self, tenant_id: str, connection_id: str) -> SyncConnection | None:
        """Return a single connection or ``None``."""
        return self._store.get(tenant_id, {}).get(connection_id)

    # ---- mutations ----

    def create(self, conn: SyncConnection) -> SyncConnection:
        """Register a new connection.  Raises ``ValueError`` on duplicate id."""
        tenant = conn.tenant_id
        bucket = self._store.setdefault(tenant, {})
        if conn.id in bucket:
            raise ValueError(f"Connection {conn.id} already exists for tenant {tenant}")
        bucket[conn.id] = conn
        log.info("Created sync connection %s for tenant %s (%s)", conn.id, tenant, conn.provider)
        return conn

    def update(self, conn: SyncConnection) -> SyncConnection:
        """Replace an existing connection in the store."""
        bucket = self._store.get(conn.tenant_id, {})
        if conn.id not in bucket:
            raise KeyError(f"Connection {conn.id} not found for tenant {conn.tenant_id}")
        bucket[conn.id] = conn
        return conn

    def delete(self, tenant_id: str, connection_id: str) -> bool:
        """Remove a connection.  Returns ``True`` if it existed."""
        bucket = self._store.get(tenant_id, {})
        if connection_id in bucket:
            del bucket[connection_id]
            log.info("Deleted sync connection %s for tenant %s", connection_id, tenant_id)
            return True
        return False

    def set_status(
        self,
        tenant_id: str,
        connection_id: str,
        status: SyncStatus,
        *,
        error_message: str = "",
    ) -> SyncConnection | None:
        """Update just the status (and optionally error_message)."""
        conn = self.get(tenant_id, connection_id)
        if conn is None:
            return None
        conn.status = status
        conn.error_message = error_message
        return conn

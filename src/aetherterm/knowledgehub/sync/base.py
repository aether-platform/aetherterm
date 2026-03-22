"""Abstract base class for sync connectors."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SyncFile:
    """Represents a single file retrieved by a connector."""

    path: str
    name: str
    content: bytes = b""
    content_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class SyncConnector(abc.ABC):
    """Base class that every provider connector must implement.

    A connector knows how to talk to an external data source and yield files
    for ingestion into KnowledgeHub.
    """

    provider: str = ""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    @abc.abstractmethod
    async def list_files(self) -> list[SyncFile]:
        """List available files from the external source (metadata only).

        Implementations should populate ``path`` and ``name`` but may leave
        ``content`` empty.
        """
        ...

    @abc.abstractmethod
    async def sync(self) -> list[SyncFile]:
        """Fetch files from the external source with content populated.

        Returns the files that should be ingested into KnowledgeHub.
        """
        ...

    async def validate(self) -> bool:
        """Validate the connection config / credentials.

        Returns ``True`` if the connector can reach the external source.
        Default implementation always returns ``True`` (stub-friendly).
        """
        return True

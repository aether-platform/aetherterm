"""Factory for creating sync connectors by provider name."""

from __future__ import annotations

from typing import Any

from aetherterm.knowledgehub.sync.base import SyncConnector
from aetherterm.knowledgehub.sync.connectors.github import GitHubConnector
from aetherterm.knowledgehub.sync.connectors.google_drive import GoogleDriveConnector
from aetherterm.knowledgehub.sync.connectors.notion import NotionConnector
from aetherterm.knowledgehub.sync.connectors.s3 import S3Connector
from aetherterm.knowledgehub.sync.connectors.sharepoint import SharePointConnector

_PROVIDERS: dict[str, type[SyncConnector]] = {
    "google-drive": GoogleDriveConnector,
    "dropbox": GoogleDriveConnector,  # TODO: implement DropboxConnector; reuse stub for now
    "notion": NotionConnector,
    "confluence": NotionConnector,  # TODO: implement ConfluenceConnector; reuse stub for now
    "sharepoint": SharePointConnector,
    "github": GitHubConnector,
    "s3": S3Connector,
}

SUPPORTED_PROVIDERS = sorted(_PROVIDERS.keys())


def create_connector(provider: str, config: dict[str, Any]) -> SyncConnector:
    """Instantiate a :class:`SyncConnector` for the given provider.

    Raises ``ValueError`` if *provider* is not recognised.
    """
    cls = _PROVIDERS.get(provider)
    if cls is None:
        raise ValueError(
            f"Unknown sync provider: {provider!r}. "
            f"Supported: {', '.join(SUPPORTED_PROVIDERS)}"
        )
    return cls(config)

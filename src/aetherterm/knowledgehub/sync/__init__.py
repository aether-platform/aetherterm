"""Sync connector framework for KnowledgeHub.

Provides a pluggable connector system for synchronising external data sources
(Google Drive, SharePoint, Notion, GitHub, S3, ...) into the KnowledgeHub
document store.
"""

from aetherterm.knowledgehub.sync.base import SyncConnector
from aetherterm.knowledgehub.sync.factory import create_connector
from aetherterm.knowledgehub.sync.models import SyncConnection, SyncStatus
from aetherterm.knowledgehub.sync.registry import SyncConnectionRegistry

__all__ = [
    "SyncConnection",
    "SyncConnectionRegistry",
    "SyncConnector",
    "SyncStatus",
    "create_connector",
]

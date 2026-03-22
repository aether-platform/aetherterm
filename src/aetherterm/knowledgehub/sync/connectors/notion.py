"""Notion sync connector (stub)."""

from __future__ import annotations

import logging
from typing import Any

from aetherterm.knowledgehub.sync.base import SyncConnector, SyncFile

log = logging.getLogger("knowledgehub.sync.connectors.notion")


class NotionConnector(SyncConnector):
    """Stub connector for Notion.

    Config keys (not yet wired):
        - ``api_key``: Notion integration token
        - ``database_id``: Root database to sync (optional)
        - ``page_ids``: Specific page IDs to sync (optional)
    """

    provider = "notion"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.database_id = config.get("database_id", "")

    async def list_files(self) -> list[SyncFile]:
        log.info("[stub] Listing pages from Notion database=%s", self.database_id)
        return [
            SyncFile(path="/Engineering/Architecture", name="Architecture.md", content_type="text/markdown"),
            SyncFile(path="/Engineering/Onboarding", name="Onboarding.md", content_type="text/markdown"),
        ]

    async def sync(self) -> list[SyncFile]:
        log.info("[stub] Syncing pages from Notion database=%s", self.database_id)
        return [
            SyncFile(
                path="/Engineering/Architecture",
                name="Architecture.md",
                content=b"# Architecture\n\n[stub] Notion page content for Architecture",
                content_type="text/markdown",
            ),
            SyncFile(
                path="/Engineering/Onboarding",
                name="Onboarding.md",
                content=b"# Onboarding\n\n[stub] Notion page content for Onboarding",
                content_type="text/markdown",
            ),
        ]

"""Google Drive sync connector (stub)."""

from __future__ import annotations

import logging
from typing import Any

from aetherterm.knowledgehub.sync.base import SyncConnector, SyncFile

log = logging.getLogger("knowledgehub.sync.connectors.google_drive")


class GoogleDriveConnector(SyncConnector):
    """Stub connector for Google Drive.

    Config keys (not yet wired):
        - ``credentials_json``: OAuth2 credentials
        - ``folder_id``: Root folder to sync
    """

    provider = "google-drive"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.folder_id = config.get("folder_id", "root")

    async def list_files(self) -> list[SyncFile]:
        log.info("[stub] Listing files from Google Drive folder=%s", self.folder_id)
        return [
            SyncFile(path="/My Drive/report.pdf", name="report.pdf", content_type="application/pdf"),
            SyncFile(path="/My Drive/notes.docx", name="notes.docx", content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ]

    async def sync(self) -> list[SyncFile]:
        log.info("[stub] Syncing files from Google Drive folder=%s", self.folder_id)
        return [
            SyncFile(
                path="/My Drive/report.pdf",
                name="report.pdf",
                content=b"[stub] Google Drive PDF content",
                content_type="application/pdf",
            ),
            SyncFile(
                path="/My Drive/notes.docx",
                name="notes.docx",
                content=b"[stub] Google Drive DOCX content",
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        ]

"""SharePoint sync connector (stub)."""

from __future__ import annotations

import logging
from typing import Any

from aetherterm.knowledgehub.sync.base import SyncConnector, SyncFile

log = logging.getLogger("knowledgehub.sync.connectors.sharepoint")


class SharePointConnector(SyncConnector):
    """Stub connector for Microsoft SharePoint.

    Config keys (not yet wired):
        - ``site_url``: SharePoint site URL
        - ``client_id``: Azure AD app client ID
        - ``client_secret``: Azure AD app client secret
        - ``library``: Document library name (default: "Documents")
    """

    provider = "sharepoint"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.site_url = config.get("site_url", "")
        self.library = config.get("library", "Documents")

    async def list_files(self) -> list[SyncFile]:
        log.info("[stub] Listing files from SharePoint site=%s lib=%s", self.site_url, self.library)
        return [
            SyncFile(path="/Documents/handbook.pdf", name="handbook.pdf", content_type="application/pdf"),
            SyncFile(path="/Documents/policy.docx", name="policy.docx", content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ]

    async def sync(self) -> list[SyncFile]:
        log.info("[stub] Syncing files from SharePoint site=%s lib=%s", self.site_url, self.library)
        return [
            SyncFile(
                path="/Documents/handbook.pdf",
                name="handbook.pdf",
                content=b"[stub] SharePoint PDF content",
                content_type="application/pdf",
            ),
            SyncFile(
                path="/Documents/policy.docx",
                name="policy.docx",
                content=b"[stub] SharePoint DOCX content",
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        ]

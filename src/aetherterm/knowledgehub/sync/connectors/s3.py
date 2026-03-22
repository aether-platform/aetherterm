"""Amazon S3 sync connector (stub)."""

from __future__ import annotations

import logging
from typing import Any

from aetherterm.knowledgehub.sync.base import SyncConnector, SyncFile

log = logging.getLogger("knowledgehub.sync.connectors.s3")


class S3Connector(SyncConnector):
    """Stub connector for Amazon S3 (and S3-compatible stores).

    Config keys (not yet wired):
        - ``bucket``: S3 bucket name
        - ``prefix``: Key prefix / folder (default: "")
        - ``region``: AWS region (default: "us-east-1")
        - ``access_key_id``: AWS access key (optional, uses default chain)
        - ``secret_access_key``: AWS secret key (optional)
        - ``endpoint_url``: Custom endpoint for S3-compatible stores (optional)
    """

    provider = "s3"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.bucket = config.get("bucket", "")
        self.prefix = config.get("prefix", "")

    async def list_files(self) -> list[SyncFile]:
        log.info("[stub] Listing objects from s3://%s/%s", self.bucket, self.prefix)
        return [
            SyncFile(path=f"{self.prefix}reports/q4.pdf", name="q4.pdf", content_type="application/pdf"),
            SyncFile(path=f"{self.prefix}data/export.csv", name="export.csv", content_type="text/csv"),
        ]

    async def sync(self) -> list[SyncFile]:
        log.info("[stub] Syncing objects from s3://%s/%s", self.bucket, self.prefix)
        return [
            SyncFile(
                path=f"{self.prefix}reports/q4.pdf",
                name="q4.pdf",
                content=b"[stub] S3 PDF content",
                content_type="application/pdf",
            ),
            SyncFile(
                path=f"{self.prefix}data/export.csv",
                name="export.csv",
                content=b"[stub] S3 CSV content",
                content_type="text/csv",
            ),
        ]

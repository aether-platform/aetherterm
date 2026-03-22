"""GitHub sync connector — partially real implementation.

Clones a repository (or pulls if already cloned), then walks the ``docs/``
directory and returns the files for ingestion.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from aetherterm.knowledgehub.sync.base import SyncConnector, SyncFile

log = logging.getLogger("knowledgehub.sync.connectors.github")

# File extensions we consider documentation-worthy
_DOC_EXTENSIONS = {
    ".md", ".mdx", ".txt", ".rst", ".adoc",
    ".pdf", ".docx", ".html", ".htm",
    ".yaml", ".yml", ".json", ".toml",
}

# Maximum file size to ingest (10 MB)
_MAX_FILE_SIZE = 10 * 1024 * 1024


class GitHubConnector(SyncConnector):
    """Connector for GitHub repositories.

    Performs a real ``git clone`` (shallow) and walks the repository tree to
    collect documentation files.

    Config keys:
        - ``repo_url``: HTTPS clone URL (required)
        - ``branch``: Branch to sync (default: main)
        - ``paths``: List of directory paths to sync (default: ["docs/"])
        - ``token``: GitHub PAT for private repos (optional)
        - ``extensions``: Additional file extensions to include (optional)
    """

    provider = "github"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.repo_url: str = config.get("repo_url", "")
        self.branch: str = config.get("branch", "main")
        self.paths: list[str] = config.get("paths", ["docs/"])
        self.token: str = config.get("token", "")
        self.extensions: set[str] = _DOC_EXTENSIONS | set(config.get("extensions", []))
        self._clone_dir: str | None = None

    # ---- internal helpers ----

    def _authenticated_url(self) -> str:
        """Inject PAT into HTTPS URL when a token is configured."""
        url = self.repo_url
        if self.token and url.startswith("https://"):
            url = url.replace("https://", f"https://x-access-token:{self.token}@", 1)
        return url

    def _clone_repo(self) -> Path:
        """Shallow-clone the repository into a temp directory."""
        clone_dir = tempfile.mkdtemp(prefix="knowledgehub-github-")
        self._clone_dir = clone_dir

        cmd = [
            "git", "clone",
            "--depth", "1",
            "--branch", self.branch,
            "--single-branch",
            self._authenticated_url(),
            clone_dir,
        ]
        log.info("Cloning %s (branch=%s) into %s", self.repo_url, self.branch, clone_dir)

        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            log.error("git clone failed: %s", exc.stderr)
            raise RuntimeError(f"git clone failed: {exc.stderr}") from exc

        return Path(clone_dir)

    def _walk_paths(self, repo_root: Path) -> list[Path]:
        """Walk configured paths inside the cloned repo and return matching files."""
        results: list[Path] = []
        for rel in self.paths:
            target = repo_root / rel
            if not target.exists():
                log.warning("Path %s does not exist in repo", rel)
                continue
            if target.is_file():
                results.append(target)
                continue
            for root, _dirs, files in os.walk(target):
                for fname in files:
                    fpath = Path(root) / fname
                    if fpath.suffix.lower() in self.extensions and fpath.stat().st_size <= _MAX_FILE_SIZE:
                        results.append(fpath)
        return results

    def _cleanup(self) -> None:
        """Remove temporary clone directory."""
        if self._clone_dir and os.path.isdir(self._clone_dir):
            shutil.rmtree(self._clone_dir, ignore_errors=True)
            self._clone_dir = None

    # ---- SyncConnector interface ----

    async def list_files(self) -> list[SyncFile]:
        if not self.repo_url:
            log.warning("No repo_url configured — returning empty list")
            return []

        try:
            repo_root = self._clone_repo()
            paths = self._walk_paths(repo_root)
            return [
                SyncFile(
                    path=str(p.relative_to(repo_root)),
                    name=p.name,
                    content_type=self._guess_content_type(p),
                )
                for p in paths
            ]
        finally:
            self._cleanup()

    async def sync(self) -> list[SyncFile]:
        if not self.repo_url:
            log.warning("No repo_url configured — returning empty list")
            return []

        try:
            repo_root = self._clone_repo()
            paths = self._walk_paths(repo_root)
            files: list[SyncFile] = []
            for p in paths:
                try:
                    content = p.read_bytes()
                except Exception as exc:
                    log.warning("Failed to read %s: %s", p, exc)
                    continue
                files.append(
                    SyncFile(
                        path=str(p.relative_to(repo_root)),
                        name=p.name,
                        content=content,
                        content_type=self._guess_content_type(p),
                    )
                )
            log.info("GitHub sync complete: %d files from %s", len(files), self.repo_url)
            return files
        finally:
            self._cleanup()

    async def validate(self) -> bool:
        """Check that the repo URL is reachable via ``git ls-remote``."""
        if not self.repo_url:
            return False
        try:
            subprocess.run(
                ["git", "ls-remote", "--exit-code", self._authenticated_url()],
                capture_output=True,
                timeout=30,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def _guess_content_type(path: Path) -> str:
        ext = path.suffix.lower()
        mapping = {
            ".md": "text/markdown",
            ".mdx": "text/markdown",
            ".txt": "text/plain",
            ".rst": "text/x-rst",
            ".html": "text/html",
            ".htm": "text/html",
            ".pdf": "application/pdf",
            ".json": "application/json",
            ".yaml": "text/yaml",
            ".yml": "text/yaml",
            ".toml": "application/toml",
        }
        return mapping.get(ext, "application/octet-stream")

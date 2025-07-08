"""
File Utilities - Infrastructure Layer

Common file operations and utilities used across the application.
"""

import os
import shutil
import tempfile
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
from datetime import datetime

log = logging.getLogger("aetherterm.infrastructure.file_utils")


class FileUtilities:
    """Centralized file operations and utilities."""

    @staticmethod
    def ensure_directory(path: Union[str, Path]) -> bool:
        """Ensure directory exists, create if necessary."""
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            log.error(f"Failed to ensure directory {path}: {e}")
            return False

    @staticmethod
    def safe_write_file(path: Union[str, Path], content: str, backup: bool = True) -> bool:
        """Safely write file with optional backup."""
        try:
            path = Path(path)

            # Create backup if file exists and backup is requested
            if backup and path.exists():
                backup_path = path.with_suffix(
                    path.suffix + f".backup.{int(datetime.now().timestamp())}"
                )
                shutil.copy2(path, backup_path)
                log.debug(f"Created backup: {backup_path}")

            # Write to temporary file first
            with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as tmp_file:
                tmp_file.write(content)
                tmp_path = tmp_file.name

            # Atomic move
            shutil.move(tmp_path, path)
            log.debug(f"Successfully wrote file: {path}")
            return True

        except Exception as e:
            log.error(f"Failed to write file {path}: {e}")
            return False

    @staticmethod
    def safe_read_file(path: Union[str, Path], encoding: str = "utf-8") -> Optional[str]:
        """Safely read file content."""
        try:
            path = Path(path)
            if not path.exists():
                log.warning(f"File does not exist: {path}")
                return None

            with open(path, "r", encoding=encoding) as file:
                return file.read()

        except Exception as e:
            log.error(f"Failed to read file {path}: {e}")
            return None

    @staticmethod
    def get_file_info(path: Union[str, Path]) -> Optional[Dict[str, Any]]:
        """Get comprehensive file information."""
        try:
            path = Path(path)
            if not path.exists():
                return None

            stat = path.stat()
            return {
                "path": str(path),
                "name": path.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime),
                "created": datetime.fromtimestamp(stat.st_ctime),
                "is_file": path.is_file(),
                "is_dir": path.is_dir(),
                "permissions": oct(stat.st_mode)[-3:],
                "owner_readable": os.access(path, os.R_OK),
                "owner_writable": os.access(path, os.W_OK),
                "owner_executable": os.access(path, os.X_OK),
            }

        except Exception as e:
            log.error(f"Failed to get file info for {path}: {e}")
            return None

    @staticmethod
    def cleanup_old_files(
        directory: Union[str, Path],
        pattern: str = "*",
        max_age_days: int = 7,
        dry_run: bool = False,
    ) -> List[str]:
        """Clean up old files matching pattern."""
        try:
            directory = Path(directory)
            if not directory.exists():
                return []

            cutoff_time = datetime.now().timestamp() - (max_age_days * 24 * 3600)
            cleaned_files = []

            for file_path in directory.glob(pattern):
                if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                    if not dry_run:
                        file_path.unlink()
                    cleaned_files.append(str(file_path))
                    log.debug(f"{'Would delete' if dry_run else 'Deleted'}: {file_path}")

            return cleaned_files

        except Exception as e:
            log.error(f"Failed to cleanup files in {directory}: {e}")
            return []

    @staticmethod
    def copy_with_progress(
        source: Union[str, Path], destination: Union[str, Path], callback=None
    ) -> bool:
        """Copy file with optional progress callback."""
        try:
            source = Path(source)
            destination = Path(destination)

            if not source.exists():
                log.error(f"Source file does not exist: {source}")
                return False

            # Ensure destination directory exists
            FileUtilities.ensure_directory(destination.parent)

            # Copy with progress tracking
            total_size = source.stat().st_size
            copied_size = 0

            with open(source, "rb") as src, open(destination, "wb") as dst:
                while True:
                    chunk = src.read(8192)  # 8KB chunks
                    if not chunk:
                        break
                    dst.write(chunk)
                    copied_size += len(chunk)

                    if callback:
                        progress = (copied_size / total_size) * 100 if total_size > 0 else 100
                        callback(progress, copied_size, total_size)

            log.info(f"Successfully copied {source} to {destination}")
            return True

        except Exception as e:
            log.error(f"Failed to copy {source} to {destination}: {e}")
            return False

    @staticmethod
    def get_directory_size(path: Union[str, Path]) -> int:
        """Get total size of directory and all subdirectories."""
        try:
            path = Path(path)
            total_size = 0

            for file_path in path.rglob("*"):
                if file_path.is_file():
                    try:
                        total_size += file_path.stat().st_size
                    except (OSError, IOError):
                        # Skip files that can't be accessed
                        continue

            return total_size

        except Exception as e:
            log.error(f"Failed to get directory size for {path}: {e}")
            return 0

    @staticmethod
    def create_temp_directory(prefix: str = "aetherterm_") -> Optional[Path]:
        """Create a temporary directory."""
        try:
            temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
            log.debug(f"Created temporary directory: {temp_dir}")
            return temp_dir
        except Exception as e:
            log.error(f"Failed to create temporary directory: {e}")
            return None

    @staticmethod
    def cleanup_temp_directory(temp_dir: Union[str, Path]) -> bool:
        """Clean up temporary directory."""
        try:
            temp_dir = Path(temp_dir)
            if temp_dir.exists() and temp_dir.is_dir():
                shutil.rmtree(temp_dir)
                log.debug(f"Cleaned up temporary directory: {temp_dir}")
                return True
            return False
        except Exception as e:
            log.error(f"Failed to cleanup temporary directory {temp_dir}: {e}")
            return False

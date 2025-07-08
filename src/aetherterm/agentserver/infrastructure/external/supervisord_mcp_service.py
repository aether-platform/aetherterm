"""
Supervisord MCP Service Integration

This module integrates the existing supervisord-mcp package with AetherTerm
to provide process management capabilities through MCP protocol.
"""

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import psutil

log = logging.getLogger(__name__)


class SupervisordMCPService:
    """
    Service for integrating Supervisord process management via MCP protocol.
    """

    def __init__(
        self,
        supervisord_url: str = "http://127.0.0.1:9001/RPC2",
        mcp_server_path: Optional[str] = None,
        config_path: Optional[str] = None,
    ):
        self.supervisord_url = supervisord_url
        self.mcp_server_path = mcp_server_path or self._find_mcp_server()
        self.config_path = config_path or self._find_supervisord_config()
        self._mcp_process: Optional[subprocess.Popen] = None
        self._is_running = False

    def _find_mcp_server(self) -> str:
        """Find the supervisord-mcp executable."""
        # Check if in the same workspace
        workspace_path = Path(__file__).parents[8] / "app" / "mcp" / "supervisord"
        if workspace_path.exists():
            return str(workspace_path / "src" / "supervisord_mcp" / "main.py")

        # Check if installed globally
        try:
            result = subprocess.run(["which", "supervisord-mcp"], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

        # Fallback to python module
        return "supervisord_mcp.main"

    def _find_supervisord_config(self) -> str:
        """Find supervisord configuration file."""
        possible_paths = [
            "/etc/supervisord.conf",
            "/etc/supervisor/supervisord.conf",
            "./supervisord.conf",
            str(Path.home() / "supervisord.conf"),
        ]

        for path in possible_paths:
            if os.path.exists(path):
                return path

        # Return default path for creation
        return "./supervisord.conf"

    async def start_mcp_server(self) -> bool:
        """Start the supervisord MCP server."""
        if self._is_running:
            log.info("Supervisord MCP server is already running")
            return True

        try:
            # Ensure supervisord is running
            await self._ensure_supervisord_running()

            # Start MCP server
            cmd = [
                sys.executable,
                "-c",
                f"from {self.mcp_server_path.replace('.py', '').replace('/', '.')} import main; main()",
            ]

            if self.mcp_server_path.endswith(".py"):
                cmd = [sys.executable, self.mcp_server_path, "mcp"]

            self._mcp_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=dict(os.environ, SUPERVISORD_SERVER_URL=self.supervisord_url),
            )

            # Wait a bit to see if it starts successfully
            await asyncio.sleep(1)

            if self._mcp_process.poll() is None:
                self._is_running = True
                log.info("Supervisord MCP server started successfully")
                return True
            else:
                stdout, stderr = self._mcp_process.communicate()
                log.error(f"Failed to start MCP server: {stderr.decode()}")
                return False

        except Exception as e:
            log.error(f"Error starting supervisord MCP server: {e}")
            return False

    async def stop_mcp_server(self) -> bool:
        """Stop the supervisord MCP server."""
        if not self._is_running or not self._mcp_process:
            return True

        try:
            self._mcp_process.terminate()

            # Wait for graceful shutdown
            try:
                await asyncio.wait_for(
                    asyncio.create_task(self._wait_for_process_end()), timeout=5.0
                )
            except asyncio.TimeoutError:
                # Force kill if not responsive
                self._mcp_process.kill()
                await asyncio.create_task(self._wait_for_process_end())

            self._is_running = False
            self._mcp_process = None
            log.info("Supervisord MCP server stopped")
            return True

        except Exception as e:
            log.error(f"Error stopping supervisord MCP server: {e}")
            return False

    async def _wait_for_process_end(self) -> None:
        """Wait for process to end asynchronously."""
        if self._mcp_process:
            while self._mcp_process.poll() is None:
                await asyncio.sleep(0.1)

    async def _ensure_supervisord_running(self) -> bool:
        """Ensure supervisord daemon is running."""
        try:
            # Check if supervisord is running
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    if "supervisord" in proc.info["name"]:
                        log.info("Supervisord is already running")
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # Try to start supervisord
            log.info("Starting supervisord daemon")
            result = await asyncio.create_subprocess_exec(
                "supervisord",
                "-c",
                self.config_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                log.info("Supervisord started successfully")
                return True
            else:
                log.error(f"Failed to start supervisord: {stderr.decode()}")
                return False

        except Exception as e:
            log.error(f"Error ensuring supervisord is running: {e}")
            return False

    async def get_process_list(self) -> List[Dict[str, Any]]:
        """Get list of processes from supervisord."""
        try:
            # Use the supervisord-mcp CLI to get process list
            result = await asyncio.create_subprocess_exec(
                sys.executable,
                self.mcp_server_path,
                "list-processes",
                "--server-url",
                self.supervisord_url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                import json

                return json.loads(stdout.decode())
            else:
                log.error(f"Error getting process list: {stderr.decode()}")
                return []

        except Exception as e:
            log.error(f"Error getting process list: {e}")
            return []

    async def start_process(self, name: str) -> Dict[str, Any]:
        """Start a process via supervisord."""
        try:
            result = await asyncio.create_subprocess_exec(
                sys.executable,
                self.mcp_server_path,
                "start",
                name,
                "--server-url",
                self.supervisord_url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                return {"status": "ok", "message": f"Process {name} started"}
            else:
                return {"status": "error", "message": stderr.decode()}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def stop_process(self, name: str) -> Dict[str, Any]:
        """Stop a process via supervisord."""
        try:
            result = await asyncio.create_subprocess_exec(
                sys.executable,
                self.mcp_server_path,
                "stop",
                name,
                "--server-url",
                self.supervisord_url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                return {"status": "ok", "message": f"Process {name} stopped"}
            else:
                return {"status": "error", "message": stderr.decode()}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def restart_process(self, name: str) -> Dict[str, Any]:
        """Restart a process via supervisord."""
        try:
            result = await asyncio.create_subprocess_exec(
                sys.executable,
                self.mcp_server_path,
                "restart",
                name,
                "--server-url",
                self.supervisord_url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                return {"status": "ok", "message": f"Process {name} restarted"}
            else:
                return {"status": "error", "message": stderr.decode()}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def get_process_logs(self, name: str, lines: int = 100) -> Dict[str, Any]:
        """Get process logs via supervisord."""
        try:
            result = await asyncio.create_subprocess_exec(
                sys.executable,
                self.mcp_server_path,
                "logs",
                name,
                "--server-url",
                self.supervisord_url,
                "--lines",
                str(lines),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                return {"status": "ok", "logs": stdout.decode()}
            else:
                return {"status": "error", "message": stderr.decode()}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def is_running(self) -> bool:
        """Check if MCP server is running."""
        return self._is_running and self._mcp_process and self._mcp_process.poll() is None

    async def get_status(self) -> Dict[str, Any]:
        """Get status of supervisord MCP integration."""
        return {
            "mcp_server_running": self.is_running(),
            "supervisord_url": self.supervisord_url,
            "config_path": self.config_path,
            "mcp_server_path": self.mcp_server_path,
        }


# Singleton instance for use across the application
_supervisord_mcp_service: Optional[SupervisordMCPService] = None


def get_supervisord_mcp_service() -> SupervisordMCPService:
    """Get the singleton supervisord MCP service instance."""
    global _supervisord_mcp_service
    if _supervisord_mcp_service is None:
        _supervisord_mcp_service = SupervisordMCPService()
    return _supervisord_mcp_service


async def initialize_supervisord_mcp() -> bool:
    """Initialize the supervisord MCP service."""
    service = get_supervisord_mcp_service()
    return await service.start_mcp_server()


async def shutdown_supervisord_mcp() -> bool:
    """Shutdown the supervisord MCP service."""
    service = get_supervisord_mcp_service()
    return await service.stop_mcp_server()

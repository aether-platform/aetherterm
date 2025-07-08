"""
System Utilities - Infrastructure Layer

Common system operations and utilities for process management, resource monitoring, etc.
"""

import os
import sys
import psutil
import platform
import subprocess
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from pathlib import Path

log = logging.getLogger("aetherterm.infrastructure.system_utils")


class SystemUtilities:
    """Centralized system operations and utilities."""

    @staticmethod
    def get_system_info() -> Dict[str, Any]:
        """Get comprehensive system information."""
        try:
            return {
                "platform": {
                    "system": platform.system(),
                    "release": platform.release(),
                    "version": platform.version(),
                    "machine": platform.machine(),
                    "processor": platform.processor(),
                    "architecture": platform.architecture(),
                    "python_version": platform.python_version(),
                    "hostname": platform.node(),
                },
                "cpu": {
                    "count": psutil.cpu_count(),
                    "count_logical": psutil.cpu_count(logical=True),
                    "usage_percent": psutil.cpu_percent(interval=1),
                    "frequency": psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None,
                },
                "memory": {
                    "total": psutil.virtual_memory().total,
                    "available": psutil.virtual_memory().available,
                    "used": psutil.virtual_memory().used,
                    "percent": psutil.virtual_memory().percent,
                    "swap_total": psutil.swap_memory().total,
                    "swap_used": psutil.swap_memory().used,
                    "swap_percent": psutil.swap_memory().percent,
                },
                "disk": {
                    "usage": psutil.disk_usage("/"),
                    "io": psutil.disk_io_counters()._asdict()
                    if psutil.disk_io_counters()
                    else None,
                },
                "network": {
                    "io": psutil.net_io_counters()._asdict() if psutil.net_io_counters() else None,
                    "connections": len(psutil.net_connections()),
                },
                "boot_time": datetime.fromtimestamp(psutil.boot_time()),
                "uptime_seconds": datetime.now().timestamp() - psutil.boot_time(),
            }
        except Exception as e:
            log.error(f"Failed to get system info: {e}")
            return {}

    @staticmethod
    def get_process_info(pid: Optional[int] = None) -> Dict[str, Any]:
        """Get information about a process (current process if pid is None)."""
        try:
            process = psutil.Process(pid) if pid else psutil.Process()

            with process.oneshot():
                return {
                    "pid": process.pid,
                    "name": process.name(),
                    "status": process.status(),
                    "created": datetime.fromtimestamp(process.create_time()),
                    "cpu_percent": process.cpu_percent(),
                    "memory_info": process.memory_info()._asdict(),
                    "memory_percent": process.memory_percent(),
                    "num_threads": process.num_threads(),
                    "num_fds": process.num_fds() if hasattr(process, "num_fds") else None,
                    "cmdline": process.cmdline(),
                    "cwd": process.cwd(),
                    "environ": dict(process.environ()),
                    "connections": [conn._asdict() for conn in process.connections()],
                    "open_files": [f._asdict() for f in process.open_files()],
                }
        except Exception as e:
            log.error(f"Failed to get process info for PID {pid}: {e}")
            return {}

    @staticmethod
    def kill_process_tree(pid: int, including_parent: bool = True) -> bool:
        """Kill a process and all its children."""
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)

            # Kill children first
            for child in children:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass

            # Kill parent if requested
            if including_parent:
                try:
                    parent.kill()
                except psutil.NoSuchProcess:
                    pass

            # Wait for processes to terminate
            gone, alive = psutil.wait_procs(
                children + ([parent] if including_parent else []), timeout=5
            )

            # Force kill any remaining processes
            for p in alive:
                try:
                    p.kill()
                except psutil.NoSuchProcess:
                    pass

            log.info(f"Successfully killed process tree for PID {pid}")
            return True

        except Exception as e:
            log.error(f"Failed to kill process tree for PID {pid}: {e}")
            return False

    @staticmethod
    def run_command(
        command: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        capture_output: bool = True,
    ) -> Dict[str, Any]:
        """Run a command and return detailed results."""
        try:
            start_time = datetime.now()

            result = subprocess.run(
                command, cwd=cwd, env=env, timeout=timeout, capture_output=capture_output, text=True
            )

            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            return {
                "command": command,
                "return_code": result.returncode,
                "stdout": result.stdout if capture_output else None,
                "stderr": result.stderr if capture_output else None,
                "execution_time": execution_time,
                "start_time": start_time,
                "end_time": end_time,
                "success": result.returncode == 0,
                "cwd": cwd,
                "env_vars": env,
            }

        except subprocess.TimeoutExpired as e:
            log.error(f"Command timeout: {command}")
            return {
                "command": command,
                "return_code": -1,
                "stdout": e.stdout if hasattr(e, "stdout") else None,
                "stderr": e.stderr if hasattr(e, "stderr") else None,
                "error": "timeout",
                "timeout": timeout,
                "success": False,
            }
        except Exception as e:
            log.error(f"Failed to run command {command}: {e}")
            return {"command": command, "return_code": -1, "error": str(e), "success": False}

    @staticmethod
    def get_environment_variables() -> Dict[str, str]:
        """Get all environment variables."""
        return dict(os.environ)

    @staticmethod
    def set_environment_variable(name: str, value: str) -> bool:
        """Set an environment variable."""
        try:
            os.environ[name] = value
            return True
        except Exception as e:
            log.error(f"Failed to set environment variable {name}: {e}")
            return False

    @staticmethod
    def get_disk_usage(path: str = "/") -> Dict[str, Any]:
        """Get disk usage information for a path."""
        try:
            usage = psutil.disk_usage(path)
            return {
                "path": path,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": (usage.used / usage.total) * 100 if usage.total > 0 else 0,
            }
        except Exception as e:
            log.error(f"Failed to get disk usage for {path}: {e}")
            return {}

    @staticmethod
    def find_processes_by_name(name: str) -> List[Dict[str, Any]]:
        """Find all processes with a given name."""
        try:
            processes = []
            for proc in psutil.process_iter(["pid", "name", "create_time", "memory_percent"]):
                if name.lower() in proc.info["name"].lower():
                    processes.append(
                        {
                            "pid": proc.info["pid"],
                            "name": proc.info["name"],
                            "created": datetime.fromtimestamp(proc.info["create_time"]),
                            "memory_percent": proc.info["memory_percent"],
                        }
                    )
            return processes
        except Exception as e:
            log.error(f"Failed to find processes by name {name}: {e}")
            return []

    @staticmethod
    def get_resource_limits() -> Dict[str, Any]:
        """Get system resource limits."""
        try:
            import resource

            limits = {}
            limit_names = [
                "RLIMIT_CPU",
                "RLIMIT_FSIZE",
                "RLIMIT_DATA",
                "RLIMIT_STACK",
                "RLIMIT_CORE",
                "RLIMIT_RSS",
                "RLIMIT_NPROC",
                "RLIMIT_NOFILE",
                "RLIMIT_MEMLOCK",
                "RLIMIT_AS",
            ]

            for limit_name in limit_names:
                if hasattr(resource, limit_name):
                    limit_value = getattr(resource, limit_name)
                    soft, hard = resource.getrlimit(limit_value)
                    limits[limit_name] = {
                        "soft": soft,
                        "hard": hard,
                        "unlimited_soft": soft == resource.RLIM_INFINITY,
                        "unlimited_hard": hard == resource.RLIM_INFINITY,
                    }

            return limits

        except ImportError:
            log.warning("Resource module not available on this platform")
            return {}
        except Exception as e:
            log.error(f"Failed to get resource limits: {e}")
            return {}

    @staticmethod
    def check_dependencies() -> Dict[str, bool]:
        """Check if required system dependencies are available."""
        dependencies = {
            "python": sys.version_info >= (3, 8),
            "psutil": True,  # Already imported successfully
        }

        # Check for optional dependencies
        optional_deps = ["docker", "kubernetes", "redis", "postgresql"]

        for dep in optional_deps:
            try:
                subprocess.run([dep, "--version"], capture_output=True, timeout=5)
                dependencies[dep] = True
            except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
                dependencies[dep] = False

        return dependencies

    @staticmethod
    def get_user_info() -> Dict[str, Any]:
        """Get current user information."""
        try:
            import pwd
            import grp

            uid = os.getuid()
            gid = os.getgid()
            user_info = pwd.getpwuid(uid)
            group_info = grp.getgrgid(gid)

            return {
                "username": user_info.pw_name,
                "uid": uid,
                "gid": gid,
                "home_directory": user_info.pw_dir,
                "shell": user_info.pw_shell,
                "group_name": group_info.gr_name,
                "groups": [grp.getgrgid(g).gr_name for g in os.getgroups()],
            }

        except ImportError:
            # Windows doesn't have pwd/grp modules
            return {
                "username": os.getenv("USERNAME") or os.getenv("USER"),
                "home_directory": os.path.expanduser("~"),
                "shell": os.getenv("SHELL", "/bin/bash"),
            }
        except Exception as e:
            log.error(f"Failed to get user info: {e}")
            return {}

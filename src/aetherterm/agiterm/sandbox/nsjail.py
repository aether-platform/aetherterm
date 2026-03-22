"""nsjail sandbox backend.

Lightweight process-level isolation using nsjail.
Multiple tenants/users share a single Pod; nsjail provides:
  - Filesystem isolation (bind mount per tenant/user)
  - PID namespace isolation
  - Resource limits (memory, CPU time, PIDs)
  - Network is shared (AI tools need API access)

Requires: nsjail binary in PATH.
"""

from __future__ import annotations

import logging
import os
import shutil
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("agiterm.sandbox.nsjail")

NSJAIL_BIN = os.environ.get("NSJAIL_BIN", "nsjail")
WORKSPACE_BASE = os.environ.get(
    "NSJAIL_WORKSPACE_BASE", "/tmp/aetherterm-workspaces"
)


@dataclass
class NsjailLimits:
    time_limit: int = 3600  # seconds (0 = unlimited)
    memory_mb: int = 4096
    max_pids: int = 256
    max_cpus: int = 2


@dataclass
class NsjailSandbox:
    """Per-session nsjail sandbox state."""

    tenant_id: str
    username: str
    session_id: str
    host_workspace: str
    cfg_path: str
    limits: NsjailLimits = field(default_factory=NsjailLimits)


class NsjailBackend:
    """nsjail-based sandbox backend.

    Implements SandboxBackend protocol.
    """

    def __init__(self) -> None:
        self._sandboxes: dict[str, NsjailSandbox] = {}  # session_id -> sandbox

    @property
    def backend_type(self) -> str:
        return "nsjail"

    @staticmethod
    def _workspace_dir(tenant_id: str, username: str) -> str:
        return os.path.join(WORKSPACE_BASE, tenant_id, username)

    @staticmethod
    def _cfg_dir() -> str:
        d = os.path.join(WORKSPACE_BASE, ".nsjail-configs")
        os.makedirs(d, exist_ok=True)
        return d

    @staticmethod
    def _generate_config(
        workspace: str,
        username: str,
        limits: NsjailLimits,
        env: dict[str, str],
    ) -> str:
        """Generate nsjail protobuf config."""
        env_lines = "\n".join(
            f'envar: "{k}={v}"' for k, v in env.items()
        )

        return textwrap.dedent(f"""\
            name: "aetherterm-sandbox"
            mode: ONCE

            # Namespaces
            clone_newpid: true
            clone_newns: true
            clone_newipc: true
            clone_newnet: false  # shared — AI tools need API access
            clone_newuts: true

            # User mapping
            uidmap {{
                inside_id: "1000"
                outside_id: "{os.getuid()}"
                count: 1
            }}
            gidmap {{
                inside_id: "1000"
                outside_id: "{os.getgid()}"
                count: 1
            }}

            # Resource limits
            rlimit_as: {limits.memory_mb}
            rlimit_cpu_type: SOFT
            rlimit_cpu: {limits.time_limit}
            time_limit: {limits.time_limit}
            detect_cgroupv2: true
            cgroup_pids_max: {limits.max_pids}
            cgroup_mem_max: {limits.memory_mb * 1024 * 1024}

            # Filesystem — read-only root + writable workspace
            mount {{
                src: "/"
                dst: "/"
                is_bind: true
                rw: false
            }}
            mount {{
                src: "{workspace}"
                dst: "/workspace"
                is_bind: true
                rw: true
            }}
            mount {{
                dst: "/tmp"
                fstype: "tmpfs"
                rw: true
            }}
            mount {{
                dst: "/dev"
                fstype: "tmpfs"
                rw: true
            }}
            mount {{
                src: "/dev/null"
                dst: "/dev/null"
                is_bind: true
                rw: true
            }}
            mount {{
                src: "/dev/urandom"
                dst: "/dev/urandom"
                is_bind: true
                rw: false
            }}
            mount {{
                dst: "/proc"
                fstype: "proc"
                rw: false
            }}

            cwd: "/workspace"
            hostname: "sandbox"
            keep_env: false

            # Environment
            envar: "HOME=/home/{username}"
            envar: "USER={username}"
            envar: "TERM=xterm-256color"
            envar: "LANG=C.UTF-8"
            envar: "PATH=/usr/local/bin:/usr/bin:/bin"
            {env_lines}
        """)

    async def prepare(
        self,
        username: str,
        session_id: str,
        image: str,
        env: dict[str, str],
        runtime_handler: str = "",
    ) -> None:
        # Extract tenant_id from env or use username as fallback
        tenant_id = env.pop("_tenant_id", username)

        # Create isolated workspace
        workspace = self._workspace_dir(tenant_id, username)
        os.makedirs(workspace, exist_ok=True)

        limits = NsjailLimits()

        # Generate nsjail config
        cfg_content = self._generate_config(workspace, username, limits, env)
        cfg_path = os.path.join(self._cfg_dir(), f"{session_id}.cfg")
        Path(cfg_path).write_text(cfg_content)

        sandbox = NsjailSandbox(
            tenant_id=tenant_id,
            username=username,
            session_id=session_id,
            host_workspace=workspace,
            cfg_path=cfg_path,
            limits=limits,
        )
        self._sandboxes[session_id] = sandbox

        log.info(
            "nsjail sandbox prepared: session=%s tenant=%s user=%s workspace=%s",
            session_id, tenant_id, username, workspace,
        )

    def wrap_command(self, username: str, cmd: list[str]) -> list[str]:
        # Find sandbox by username (latest session)
        sandbox = None
        for s in reversed(list(self._sandboxes.values())):
            if s.username == username:
                sandbox = s
                break

        if sandbox is None:
            log.warning("No nsjail sandbox for user %s, running unwrapped", username)
            return cmd

        full_cmd = " ".join(cmd)
        return [
            NSJAIL_BIN,
            "--config", sandbox.cfg_path,
            "--", "/bin/bash", "-c", full_cmd,
        ]

    async def cleanup(self, username: str, session_id: str) -> None:
        sandbox = self._sandboxes.pop(session_id, None)
        if sandbox is None:
            return

        # Remove config file
        try:
            os.unlink(sandbox.cfg_path)
        except OSError:
            pass

        log.info("nsjail sandbox cleaned up: session=%s user=%s", session_id, username)

    async def cleanup_all(self) -> None:
        for session_id in list(self._sandboxes):
            sandbox = self._sandboxes.pop(session_id)
            try:
                os.unlink(sandbox.cfg_path)
            except OSError:
                pass
        log.info("All nsjail sandboxes cleaned up")

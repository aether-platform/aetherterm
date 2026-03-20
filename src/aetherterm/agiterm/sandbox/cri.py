"""CRI (containerd) sandbox backend.

Uses Kubernetes CRI gRPC API directly. Vendor-neutral: works with any
CRI-compliant runtime (containerd, CRI-O). Supports MicroVM runtimes
(Kata Containers, Firecracker) via runtime_handler.

Each user gets:
  - PodSandbox — network/cgroup isolation boundary
  - Container  — runs inside the PodSandbox

Dependencies (optional):
  pip install container-runtime-interface-api grpcio
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from aetherterm.agiterm.sandbox.backend import CRI_SOCKET

log = logging.getLogger("agiterm.sandbox.cri")

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")
_LABEL_PREFIX = "aetherterm.io"
_VALID_HANDLERS = frozenset({"", "runc", "kata", "kata-fc", "kata-clh", "kata-qemu"})

SANDBOX_IMAGE = os.environ.get("SANDBOX_IMAGE", "aetherterm-sandbox:latest")
RUNTIME_HANDLER = os.environ.get("SANDBOX_RUNTIME", "").strip()

_PASSTHROUGH_ENV_KEYS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_REGION",
    "NATS_URL",
)


def _validate_username(username: str) -> str:
    if not _USERNAME_RE.match(username):
        raise ValueError(f"Invalid username: {username!r}")
    return username


def _import_cri():
    import grpc as _grpc
    from cri_api.v1 import api_pb2 as _pb2
    from cri_api.v1 import api_pb2_grpc as _pb2_grpc
    return _grpc, _pb2, _pb2_grpc


# ---------------------------------------------------------------------------
# Resource limits
# ---------------------------------------------------------------------------

@dataclass
class SandboxLimits:
    cpu_milli: int = 2000
    memory_bytes: int = 4 * 1024**3
    pids_limit: int = 256
    storage_mb: int = 10240
    read_only_rootfs: bool = False
    runtime_handler: str = ""


# ---------------------------------------------------------------------------
# Per-user CRI sandbox
# ---------------------------------------------------------------------------

class CriSandbox:
    """Per-user CRI sandbox (PodSandbox + Container)."""

    def __init__(
        self,
        username: str,
        uid: int = 1000,
        gid: int = 1000,
        limits: SandboxLimits | None = None,
        env: dict[str, str] | None = None,
    ):
        self.username = _validate_username(username)
        self.uid = uid
        self.gid = gid
        self.limits = limits or SandboxLimits()
        self.env = env or {}
        self._pod_id: str = ""
        self._container_id: str = ""
        self._grpc: Any = None
        self._pb2: Any = None
        self._pb2_grpc: Any = None

    def _cri(self):
        if self._pb2 is None:
            self._grpc, self._pb2, self._pb2_grpc = _import_cri()
        return self._pb2

    @property
    def is_running(self) -> bool:
        return bool(self._container_id)

    @property
    def container_id(self) -> str:
        return self._container_id

    def _build_env(self, pb2, user_env: dict[str, str] | None = None) -> list:
        env_vars = {
            "HOME": f"/home/{self.username}",
            "USER": self.username,
            "TERM": "xterm-256color",
            "LANG": "C.UTF-8",
            "PATH": "/usr/local/bin:/usr/bin:/bin",
        }
        for key in _PASSTHROUGH_ENV_KEYS:
            val = os.environ.get(key)
            if val:
                env_vars[key] = val
        # Instance env (set at construction)
        env_vars.update(self.env)
        # Per-session env (from caller)
        if user_env:
            env_vars.update(user_env)
        return [pb2.KeyValue(key=k, value=v) for k, v in env_vars.items()]

    def _pod_sandbox_config(self):
        pb2 = self._cri()
        handler = self.limits.runtime_handler or RUNTIME_HANDLER
        if handler and handler not in _VALID_HANDLERS:
            raise ValueError(f"Invalid runtime handler: {handler!r}")

        return pb2.PodSandboxConfig(
            metadata=pb2.PodSandboxMetadata(
                name=f"aetherterm-{self.username}",
                uid=f"aetherterm-{self.username}",
                namespace="aetherterm",
            ),
            dns_config=pb2.DNSConfig(servers=["8.8.8.8", "8.8.4.4"]),
            labels={
                f"{_LABEL_PREFIX}/username": self.username,
                f"{_LABEL_PREFIX}/component": "sandbox",
            },
            annotations={
                f"{_LABEL_PREFIX}/uid": str(self.uid),
                f"{_LABEL_PREFIX}/gid": str(self.gid),
            },
            linux=pb2.LinuxPodSandboxConfig(
                security_context=pb2.LinuxSandboxSecurityContext(
                    namespace_options=pb2.NamespaceOption(
                        network=pb2.NODE,
                        pid=pb2.POD,
                        ipc=pb2.POD,
                    ),
                    run_as_user=pb2.Int64Value(value=self.uid),
                    run_as_group=pb2.Int64Value(value=self.gid),
                    seccomp=pb2.SecurityProfile(
                        profile_type=pb2.SecurityProfile.RuntimeDefault,
                    ),
                ),
            ),
        )

    def _container_config(self):
        pb2 = self._cri()
        lim = self.limits
        envs = self._build_env(pb2, self.env)

        workspace_host = f"/tmp/aetherterm-workspaces/{self.username}"
        os.makedirs(workspace_host, exist_ok=True)

        home_container = f"/home/{self.username}"

        mounts = [
            pb2.Mount(
                container_path="/workspace",
                host_path=workspace_host,
                readonly=False,
                propagation=pb2.PROPAGATION_PRIVATE,
            ),
        ]

        host_claude = os.path.expanduser("~/.claude")
        if os.path.isdir(host_claude):
            mounts.append(
                pb2.Mount(
                    container_path=f"{home_container}/.claude",
                    host_path=host_claude,
                    readonly=True,
                    propagation=pb2.PROPAGATION_PRIVATE,
                )
            )

        linux_config = pb2.LinuxContainerConfig(
            resources=pb2.LinuxContainerResources(
                cpu_period=100000,
                cpu_quota=lim.cpu_milli * 100,
                memory_limit_in_bytes=lim.memory_bytes,
                unified={"pids.max": str(lim.pids_limit)},
            ),
            security_context=pb2.LinuxContainerSecurityContext(
                run_as_user=pb2.Int64Value(value=self.uid),
                run_as_group=pb2.Int64Value(value=self.gid),
                no_new_privs=True,
                readonly_rootfs=lim.read_only_rootfs,
                seccomp=pb2.SecurityProfile(
                    profile_type=pb2.SecurityProfile.RuntimeDefault,
                ),
            ),
        )

        return pb2.ContainerConfig(
            metadata=pb2.ContainerMetadata(name=f"agent-{self.username}"),
            image=pb2.ImageSpec(image=SANDBOX_IMAGE),
            command=["/bin/bash"],
            args=["-c", "sleep infinity"],
            envs=envs,
            mounts=mounts,
            labels={
                f"{_LABEL_PREFIX}/username": self.username,
                f"{_LABEL_PREFIX}/component": "agent",
            },
            linux=linux_config,
        )

    # --- Synchronous lifecycle (safe inside existing event loop) ---

    def _get_sync_runtime(self):
        grpc_mod, pb2, pb2_grpc = _import_cri()
        channel = grpc_mod.insecure_channel(CRI_SOCKET)
        return pb2_grpc.RuntimeServiceStub(channel), pb2, channel

    def _cleanup_stale_pods(self, rt, pb2) -> None:
        try:
            resp = rt.ListPodSandbox(
                pb2.ListPodSandboxRequest(
                    filter=pb2.PodSandboxFilter(
                        label_selector={f"{_LABEL_PREFIX}/username": self.username}
                    )
                )
            )
            for pod in resp.items:
                log.info("Cleaning stale pod %s for user %s", pod.id[:12], self.username)
                try:
                    containers = rt.ListContainers(
                        pb2.ListContainersRequest(
                            filter=pb2.ContainerFilter(pod_sandbox_id=pod.id)
                        )
                    )
                    for c in containers.containers:
                        rt.StopContainer(pb2.StopContainerRequest(container_id=c.id, timeout=3))
                        rt.RemoveContainer(pb2.RemoveContainerRequest(container_id=c.id))
                except Exception:
                    pass
                try:
                    rt.StopPodSandbox(pb2.StopPodSandboxRequest(pod_sandbox_id=pod.id))
                    rt.RemovePodSandbox(pb2.RemovePodSandboxRequest(pod_sandbox_id=pod.id))
                except Exception:
                    pass
        except Exception as e:
            log.debug("Stale pod cleanup skipped: %s", e)

    def start_sync(self) -> str:
        if self._container_id:
            return self._container_id

        rt, pb2, channel = self._get_sync_runtime()
        handler = self.limits.runtime_handler or RUNTIME_HANDLER or ""

        try:
            self._cleanup_stale_pods(rt, pb2)

            pod_config = self._pod_sandbox_config()
            pod_resp = rt.RunPodSandbox(
                pb2.RunPodSandboxRequest(config=pod_config, runtime_handler=handler)
            )
            self._pod_id = pod_resp.pod_sandbox_id
            log.info("PodSandbox created: %s (user=%s, handler=%s)",
                     self._pod_id[:12], self.username, handler or "default")

            container_config = self._container_config()
            create_resp = rt.CreateContainer(
                pb2.CreateContainerRequest(
                    pod_sandbox_id=self._pod_id,
                    config=container_config,
                    sandbox_config=pod_config,
                )
            )
            self._container_id = create_resp.container_id

            rt.StartContainer(pb2.StartContainerRequest(container_id=self._container_id))
            log.info("Container started: %s (user=%s)", self._container_id[:12], self.username)
        finally:
            channel.close()

        return self._container_id

    def stop_sync(self) -> None:
        if not self._container_id and not self._pod_id:
            return

        rt, pb2, channel = self._get_sync_runtime()
        grpc_mod = _import_cri()[0]

        try:
            if self._container_id:
                try:
                    rt.StopContainer(pb2.StopContainerRequest(container_id=self._container_id, timeout=5))
                    rt.RemoveContainer(pb2.RemoveContainerRequest(container_id=self._container_id))
                except grpc_mod.RpcError as e:
                    log.warning("Container stop error: %s", e)
                self._container_id = ""

            if self._pod_id:
                try:
                    rt.StopPodSandbox(pb2.StopPodSandboxRequest(pod_sandbox_id=self._pod_id))
                    rt.RemovePodSandbox(pb2.RemovePodSandboxRequest(pod_sandbox_id=self._pod_id))
                except grpc_mod.RpcError as e:
                    log.warning("PodSandbox remove error: %s", e)
                self._pod_id = ""
        finally:
            channel.close()

        log.info("Sandbox stopped for user %s", self.username)

    def wrap_command(self, cmd: str) -> list[str]:
        if not self._container_id:
            self.start_sync()
        return ["crictl", "exec", "-it", self._container_id, "/bin/bash", "-c", cmd]


# ---------------------------------------------------------------------------
# CriBackend — SandboxBackend implementation
# ---------------------------------------------------------------------------

class CriBackend:
    """CRI sandbox backend managing per-user sandboxes."""

    def __init__(self) -> None:
        self._sandboxes: dict[str, CriSandbox] = {}

    @property
    def backend_type(self) -> str:
        return "cri"

    def _get_or_create(
        self,
        username: str,
        env: dict[str, str] | None = None,
        runtime_handler: str = "",
    ) -> CriSandbox:
        if username not in self._sandboxes:
            limits = SandboxLimits(runtime_handler=runtime_handler)
            self._sandboxes[username] = CriSandbox(
                username=username, limits=limits, env=env or {},
            )
        return self._sandboxes[username]

    async def prepare(
        self,
        username: str,
        session_id: str,
        image: str,
        env: dict[str, str],
        runtime_handler: str = "",
    ) -> None:
        sandbox = self._get_or_create(username, env, runtime_handler)
        if not sandbox.is_running:
            sandbox.start_sync()

    def wrap_command(self, username: str, cmd: list[str]) -> list[str]:
        sandbox = self._sandboxes.get(username)
        if not sandbox or not sandbox.is_running:
            return cmd
        full_cmd = " ".join(cmd)
        return sandbox.wrap_command(full_cmd)

    async def cleanup(self, username: str, session_id: str) -> None:
        sandbox = self._sandboxes.pop(username, None)
        if sandbox:
            sandbox.stop_sync()

    async def cleanup_all(self) -> None:
        for username in list(self._sandboxes):
            sandbox = self._sandboxes.pop(username)
            sandbox.stop_sync()

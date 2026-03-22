"""Integration tests for both sandbox backends (nsjail and CRI).

Tests the SandboxBackend protocol with real nsjail/CRI execution.
"""

import asyncio
import os
import shutil
import pytest

from aetherterm.agiterm.sandbox.backend import SandboxBackend


# ---- nsjail backend ----


@pytest.fixture
def nsjail_backend():
    if not shutil.which("nsjail"):
        pytest.skip("nsjail not installed")
    from aetherterm.agiterm.sandbox.nsjail import NsjailBackend
    return NsjailBackend()


async def test_nsjail_prepare_and_wrap(nsjail_backend):
    """nsjail: prepare creates config, wrap_command prefixes with nsjail."""
    backend = nsjail_backend

    await backend.prepare(
        username="testuser",
        session_id="test-session-001",
        image="unused",
        env={"_tenant_id": "tenant-a", "FOO": "bar"},
    )

    cmd = backend.wrap_command("testuser", ["/bin/echo", "hello"])

    assert cmd[0] == "nsjail"
    assert "--config" in cmd
    cfg_path = cmd[cmd.index("--config") + 1]
    assert os.path.exists(cfg_path)

    # Verify config contents
    cfg = open(cfg_path).read()
    assert "tenant-a" in cfg or "testuser" in cfg
    assert 'envar: "FOO=bar"' in cfg

    await backend.cleanup("testuser", "test-session-001")
    assert not os.path.exists(cfg_path)


async def test_nsjail_execute_echo(nsjail_backend):
    """nsjail: actually execute a command inside the sandbox."""
    backend = nsjail_backend

    await backend.prepare(
        username="echotest",
        session_id="test-echo-001",
        image="unused",
        env={"_tenant_id": "tenant-echo"},
    )

    cmd = backend.wrap_command("echotest", ["/bin/echo", "sandbox-works"])

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    assert b"sandbox-works" in stdout, f"stdout={stdout!r}, stderr={stderr!r}"

    await backend.cleanup("echotest", "test-echo-001")


async def test_nsjail_filesystem_isolation(nsjail_backend):
    """nsjail: workspace is isolated, host files not visible."""
    backend = nsjail_backend

    await backend.prepare(
        username="isouser",
        session_id="test-iso-001",
        image="unused",
        env={"_tenant_id": "tenant-iso"},
    )

    # Write a file in the workspace
    workspace = backend._workspace_dir("tenant-iso", "isouser")
    os.makedirs(workspace, exist_ok=True)
    with open(os.path.join(workspace, "visible.txt"), "w") as f:
        f.write("I am visible")

    # Check: file is visible inside sandbox
    cmd = backend.wrap_command("isouser", ["cat", "/workspace/visible.txt"])
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    assert b"I am visible" in stdout

    # Check: host-specific path not writable
    cmd2 = backend.wrap_command("isouser", ["touch", "/tmp/nsjail-escape-test"])
    proc2 = await asyncio.create_subprocess_exec(
        *cmd2,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc2.communicate()
    # /tmp inside nsjail is tmpfs, not host /tmp
    assert not os.path.exists("/tmp/nsjail-escape-test")

    await backend.cleanup("isouser", "test-iso-001")
    shutil.rmtree(workspace, ignore_errors=True)


async def test_nsjail_cleanup_all(nsjail_backend):
    """nsjail: cleanup_all removes all sessions."""
    backend = nsjail_backend

    for i in range(3):
        await backend.prepare(
            username=f"user{i}",
            session_id=f"sess-{i}",
            image="unused",
            env={"_tenant_id": "tenant-bulk"},
        )

    assert len(backend._sandboxes) == 3
    await backend.cleanup_all()
    assert len(backend._sandboxes) == 0


async def test_nsjail_backend_type(nsjail_backend):
    assert nsjail_backend.backend_type == "nsjail"


async def test_nsjail_is_sandbox_backend(nsjail_backend):
    assert isinstance(nsjail_backend, SandboxBackend)


# ---- CRI backend ----


@pytest.fixture
def cri_backend():
    sock = os.environ.get("CRI_SOCKET", "unix:///run/containerd/containerd.sock")
    sock_path = sock.replace("unix://", "")
    if not os.path.exists(sock_path):
        pytest.skip("containerd socket not found")
    if not shutil.which("crictl"):
        pytest.skip("crictl not installed")
    from aetherterm.agiterm.sandbox.cri import CriBackend
    return CriBackend()


async def test_cri_backend_type(cri_backend):
    assert cri_backend.backend_type == "cri"


async def test_cri_is_sandbox_backend(cri_backend):
    assert isinstance(cri_backend, SandboxBackend)


async def test_cri_prepare_wrap_cleanup(cri_backend):
    """CRI: full lifecycle — prepare, wrap, cleanup."""
    backend = cri_backend

    await backend.prepare(
        username="critest",
        session_id="cri-test-001",
        image="docker.io/library/alpine:latest",
        env={"TEST_VAR": "hello"},
    )

    cmd = backend.wrap_command("critest", ["/bin/echo", "cri-works"])
    assert "crictl" in cmd[0]

    await backend.cleanup("critest", "cri-test-001")


# ---- auto detection ----


async def test_create_backend_auto():
    """create_backend() returns a valid SandboxBackend."""
    from aetherterm.agiterm.sandbox.backend import create_backend

    backend = create_backend()
    assert isinstance(backend, SandboxBackend)
    assert backend.backend_type in ("nsjail", "cri")

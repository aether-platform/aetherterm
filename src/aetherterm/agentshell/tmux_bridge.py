"""tmux bridge — real tmux server with hooks that forward events to wm socket.

Architecture:
    tmux -S $TMUX_BRIDGE_SOCK split-window "agent cmd"
      -> real tmux creates pane
      -> after-split-window hook fires
      -> hook calls: tmux_bridge.py notify split <pane_id> <cmd>
      -> bridge sends JSON to wm socket
      -> AetherTerm pane created in web UI

Usage:
    # Start tmux server + session with hooks
    python -m aetherterm.agentshell.tmux_bridge start

    # Use normal tmux commands
    tmux -S /tmp/aetherterm-tmux-bridge.sock split-window -h "echo hello"
    tmux -S /tmp/aetherterm-tmux-bridge.sock list-panes

    # Stop
    python -m aetherterm.agentshell.tmux_bridge stop
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time

BRIDGE_SOCK = os.environ.get("TMUX_BRIDGE_SOCK", "/tmp/aetherterm-tmux-bridge.sock")
WM_SOCK = os.environ.get("WM_SOCKET", f"/tmp/aetherterm-wm-{os.getuid()}/default.sock")
SESSION_NAME = "agents"
SELF = os.path.abspath(__file__)
PYTHON = sys.executable


def _wm_send(cmd: str, args: dict) -> dict:
    """Send a command to the wm Unix socket."""
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect(WM_SOCK)
        req = json.dumps({"cmd": cmd, "args": args}) + "\n"
        s.sendall(req.encode())
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
        s.close()
        return json.loads(buf.decode().strip()) if buf else {"ok": False, "error": "no response"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _tmux(*args: str) -> str:
    """Run a tmux command against the bridge socket."""
    result = subprocess.run(
        ["tmux", "-S", BRIDGE_SOCK] + list(args),
        capture_output=True, text=True, timeout=5,
    )
    return result.stdout.strip()


def _tmux_rc(*args: str) -> int:
    result = subprocess.run(
        ["tmux", "-S", BRIDGE_SOCK] + list(args),
        capture_output=True, text=True, timeout=5,
    )
    return result.returncode


# ---------------------------------------------------------------------------
# Hook handler — called by tmux hooks
# ---------------------------------------------------------------------------

HOOK_SCRIPT = f"""'{PYTHON}' '{SELF}' notify"""


def _setup_hooks():
    """Configure tmux hooks to call back into this script."""
    hooks = {
        "after-split-window": (
            f"{HOOK_SCRIPT} split"
            " #{pane_id} #{pane_current_command} #{pane_title}"
        ),
        "after-new-window": f"{HOOK_SCRIPT} new-window #{{window_id}} #{{window_name}}",
        "pane-died": f"{HOOK_SCRIPT} pane-died #{{pane_id}}",
        "window-linked": f"{HOOK_SCRIPT} window-linked #{{window_id}} #{{window_name}}",
    }
    for hook, cmd in hooks.items():
        _tmux("set-hook", "-g", hook, f"run-shell \"{cmd}\"")


def handle_notify(argv: list[str]):
    """Handle a hook notification from tmux."""
    if not argv:
        return

    event = argv[0]
    args = argv[1:]

    _log(f"hook: {event} {args}")

    if event == "split":
        pane_id = args[0] if args else "?"
        cmd = args[1] if len(args) > 1 else ""
        title = args[2] if len(args) > 2 else pane_id
        # Forward to wm: create an AetherTerm pane that mirrors this
        resp = _wm_send("split", {
            "direction": "h",
            "cmd": cmd or "bash",
            "title": f"tmux:{title}",
        })
        _log(f"wm split -> {resp.get('ok')}")

    elif event == "new-window":
        name = args[1] if len(args) > 1 else "Shell"
        resp = _wm_send("new-window", {"title": f"tmux:{name}"})
        _log(f"wm new-window -> {resp.get('ok')}")

    elif event == "pane-died":
        pane_id = args[0] if args else "?"
        _log(f"pane died: {pane_id}")
        # Could close corresponding wm pane here


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_start():
    """Start tmux server with hooks and create initial session."""
    # Check if already running
    if _tmux_rc("has-session", "-t", SESSION_NAME) == 0:
        print(f"Session '{SESSION_NAME}' already running on {BRIDGE_SOCK}")
        print(f"  tmux -S {BRIDGE_SOCK} attach")
        return

    # Start new session (detached)
    subprocess.run(
        ["tmux", "-S", BRIDGE_SOCK, "new-session", "-d", "-s", SESSION_NAME, "-n", "main"],
        check=True,
    )

    # Setup hooks
    _setup_hooks()

    # Display info
    _tmux("set-option", "-g", "status-left", f"[{SESSION_NAME}] ")
    _tmux("set-option", "-g", "status-right", "tmux-bridge | wm sync")
    _tmux("set-option", "-g", "mouse", "on")

    print("tmux bridge started:")
    print(f"  Socket:  {BRIDGE_SOCK}")
    print(f"  Session: {SESSION_NAME}")
    print(f"  WM sync: {WM_SOCK}")
    print()
    print("Usage:")
    print(f"  tmux -S {BRIDGE_SOCK} split-window -h 'echo hello'")
    print(f"  tmux -S {BRIDGE_SOCK} list-panes")
    print(f"  tmux -S {BRIDGE_SOCK} attach")
    print()
    print("Or set alias:")
    print(f"  alias tx='tmux -S {BRIDGE_SOCK}'")


def cmd_stop():
    """Kill tmux server."""
    _tmux("kill-server")
    if os.path.exists(BRIDGE_SOCK):
        os.unlink(BRIDGE_SOCK)
    print("tmux bridge stopped")


def cmd_status():
    """Show tmux server status."""
    if _tmux_rc("has-session", "-t", SESSION_NAME) != 0:
        print("Not running")
        return 1
    print(f"Socket: {BRIDGE_SOCK}")
    print(f"Session: {SESSION_NAME}")
    print()
    print("Windows:")
    print(_tmux("list-windows", "-t", SESSION_NAME))
    print()
    print("Panes:")
    print(_tmux("list-panes", "-a"))
    return 0


def cmd_spawn(argv: list[str]):
    """Spawn an agent in a new tmux pane.

    Usage: tmux_bridge.py spawn --role coder [--agent-id ID] [--nats-url URL]
    """
    p = argparse.ArgumentParser(prog="tmux_bridge spawn")
    p.add_argument("--role", required=True)
    p.add_argument("--agent-id", default=None)
    p.add_argument("--nats-url", default=os.environ.get("NATS_URL", "nats://localhost:4222"))
    p.add_argument("--claude", action="store_true", help="Use Claude CLI with --teammate-mode tmux")
    args = p.parse_args(argv)

    agent_id = args.agent_id or f"{args.role}-{os.urandom(3).hex()}"

    if args.claude:
        cmd = "claude --dangerously-skip-permissions --teammate-mode tmux"
    else:
        cmd = (
            f"{PYTHON} -m aetherterm.agentshell.main "
            f"--agent-id {agent_id} --role {args.role} --nats-url {args.nats_url}"
        )

    # Split in tmux (hook will sync to wm)
    _tmux("split-window", "-h", "-t", SESSION_NAME, cmd)

    print(f"Spawned {agent_id} (role={args.role}) in tmux pane")
    print(f"  tmux -S {BRIDGE_SOCK} list-panes")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_LOG_PATH = "/tmp/tmux-bridge.log"


def _log(msg: str):
    try:
        with open(_LOG_PATH, "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    argv = sys.argv[1:]
    if not argv:
        print("Usage: tmux_bridge.py {start|stop|status|spawn|notify}")
        return 1

    cmd = argv[0]
    if cmd == "start":
        cmd_start()
    elif cmd == "stop":
        cmd_stop()
    elif cmd == "status":
        return cmd_status()
    elif cmd == "spawn":
        cmd_spawn(argv[1:])
    elif cmd == "notify":
        handle_notify(argv[1:])
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)

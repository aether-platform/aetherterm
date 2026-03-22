"""wm — Window/Pane manager + Agent launcher CLI.

Connects to the WindowManager Unix socket and sends JSON commands.

Usage:
    wm agent -r coder                         # interactive Claude in browser
    wm agent -r coder --nats                   # NATS-connected stub worker
    wm agent -r coder --nats --claude          # NATS-connected Claude worker
    wm agent -r reviewer --teammate            # Claude --teammate-mode
    wm new-window [-t TITLE] [-c CMD]
    wm split [-d h|v] [-c CMD] [-t TITLE]
    wm list-windows
    wm list-panes [-w WINDOW_ID]
    wm close-window WINDOW_ID
    wm close-pane PANE_ID
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys

WM_HOST = os.environ.get("WM_HOST", "localhost")
WM_PORT = os.environ.get("WM_PORT", "57575")


def _default_socket_path() -> str:
    override = os.environ.get("WM_SOCKET")
    if override:
        return override
    uid = os.getuid()
    return f"/tmp/aetherterm-wm-{uid}/default.sock"


def _find_tmux_shim_dir() -> str | None:
    """Find the directory containing the tmux-shim binary.

    Returns a PATH-prependable dir where 'tmux' resolves to our shim.
    Creates a symlink tmux -> aetherterm-tmux-shim in a temp dir if needed.
    """
    import tempfile

    # Search in PATH
    shim_path = shutil.which("aetherterm-tmux-shim")
    if not shim_path:
        # Check venv bin directory
        venv_bin = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            ".venv", "bin", "aetherterm-tmux-shim",
        )
        if os.path.exists(venv_bin):
            shim_path = venv_bin
    if not shim_path:
        return None

    # Create a temp dir with a 'tmux' symlink pointing to aetherterm-tmux-shim
    shim_dir = os.path.join(tempfile.gettempdir(), f"aetherterm-tmux-shim-{os.getuid()}")
    os.makedirs(shim_dir, exist_ok=True)
    link_path = os.path.join(shim_dir, "tmux")
    # Recreate symlink if target changed
    if os.path.islink(link_path):
        if os.readlink(link_path) != shim_path:
            os.unlink(link_path)
            os.symlink(shim_path, link_path)
    elif not os.path.exists(link_path):
        os.symlink(shim_path, link_path)
    return shim_dir


def _terminal_url(session_id: str) -> str:
    return f"http://{WM_HOST}:{WM_PORT}/terminal/session/{session_id}"


async def _send_command(socket_path: str, cmd: str, args: dict) -> dict:
    """Send a JSON command to the Unix socket and return the response."""
    try:
        reader, writer = await asyncio.open_unix_connection(socket_path)
    except (ConnectionRefusedError, FileNotFoundError) as e:
        return {"ok": False, "error": f"Cannot connect to {socket_path}: {e}"}

    req = json.dumps({"cmd": cmd, "args": args}) + "\n"
    writer.write(req.encode())
    await writer.drain()

    line = await reader.readline()
    writer.close()
    await writer.wait_closed()

    if not line:
        return {"ok": False, "error": "No response from server"}
    return json.loads(line.decode())


def _print_session(data: dict) -> None:
    """Print created session info."""
    session_id = data.get("session_id", "")
    agent_id = data.get("agent_id", "")
    role = data.get("role", "")
    if agent_id:
        print(f"  Agent: {agent_id} (role={role})")
    if session_id:
        print(f"  Terminal: {_terminal_url(session_id)}")
    print("  (browser will open automatically via WebSocket push)")


def _print_result(resp: dict) -> None:
    """Pretty-print the response."""
    if not resp.get("ok"):
        print(f"Error: {resp.get('error', 'unknown')}", file=sys.stderr)
        sys.exit(1)

    data = resp.get("data")
    if data is None:
        print("OK")
        return

    if isinstance(data, list):
        if not data:
            print("(none)")
        for item in data:
            _print_item(item)
    elif isinstance(data, dict):
        _print_item(data)
    else:
        print(data)


def _print_item(item: dict) -> None:
    """Print a single result item."""
    if "window_id" in item and "pane_count" in item:
        active = " *" if item.get("active") else ""
        print(f"  {item['window_id']}: {item['title']} ({item['pane_count']} panes){active}")
    elif "pane_id" in item and "session_id" in item:
        sid = item.get("session_id", "")
        title = item.get("title", "")
        print(f"  {item['pane_id']}: {title} (session={sid})")
        if sid:
            print(f"    -> {_terminal_url(sid)}")
    elif "direction" in item:
        print(json.dumps(item, indent=2))
    else:
        print(json.dumps(item, indent=2))


def main():
    parser = argparse.ArgumentParser(
        prog="wm",
        description="Window/Pane manager CLI — creates sessions and opens browser",
    )
    parser.add_argument(
        "--socket", "-s",
        default=_default_socket_path(),
        help=f"Unix socket path (default: {_default_socket_path()})",
    )
    parser.add_argument(
        "--no-open", "-n",
        action="store_true",
        help="Suppress browser push notification",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # agent — spawn Claude/worker agent in browser
    p = sub.add_parser("agent", aliases=["a"], help="Launch agent in browser terminal")
    p.add_argument(
        "-r", "--role", default="coder",
        help="Agent role (coder, reviewer, tester, ...)",
    )
    p.add_argument("--agent-id", default=None, help="Agent ID (auto-generated if omitted)")
    p.add_argument("--nats", action="store_true", help="Connect agent to NATS (worker mode)")
    p.add_argument("--claude", action="store_true", help="Use Claude CLI (with --nats)")
    p.add_argument(
        "--teammate", action="store_true",
        help="Launch claude --teammate-mode in-process",
    )
    p.add_argument("--model", default=None, help="Claude model override")
    p.add_argument("--workspace", "-w", default=None, help="Working directory")
    p.add_argument("--nats-url", default=None, help="NATS URL (default: nats://localhost:4222)")
    p.add_argument("-c", "--cmd", default=None, help="Custom command override")
    p.add_argument(
        "--permission-mode", default="bypassPermissions",
        choices=["default", "acceptEdits", "bypassPermissions", "plan"],
        help="Claude permission mode (default: bypassPermissions)",
    )
    p.add_argument("--system-prompt", default=None, help="System prompt for Claude")
    p.add_argument(
        "--dangerously-skip-permissions", action="store_true",
        help="Pass --dangerously-skip-permissions to claude",
    )

    # list-windows
    sub.add_parser("list-windows", aliases=["lw"], help="List all windows")

    # new-window
    p = sub.add_parser("new-window", aliases=["nw"], help="Create window + open in browser")
    p.add_argument("-t", "--title", default="Shell")
    p.add_argument("-c", "--cmd", default="")

    # split
    p = sub.add_parser("split", aliases=["sp"], help="Create new session + open in browser")
    p.add_argument("-d", "--direction", default="h", choices=["h", "v"])
    p.add_argument("-c", "--cmd", default="")
    p.add_argument("-t", "--title", default="shell")
    p.add_argument("-w", "--window-id", default=None)
    p.add_argument("-p", "--pane-id", default=None)
    p.add_argument("-r", "--ratio", type=float, default=0.5)

    # close-window
    p = sub.add_parser("close-window", aliases=["cw"], help="Close a window")
    p.add_argument("window_id")

    # close-pane
    p = sub.add_parser("close-pane", aliases=["cp"], help="Close a pane")
    p.add_argument("pane_id")

    # focus
    p = sub.add_parser("focus", aliases=["f"], help="Focus a pane")
    p.add_argument("pane_id")

    # list-panes
    p = sub.add_parser("list-panes", aliases=["lp"], help="List all leaf panes")
    p.add_argument("-w", "--window-id", default=None)

    # layout
    p = sub.add_parser("layout", aliases=["lo"], help="Show window layout tree")
    p.add_argument("-w", "--window-id", default=None)

    args = parser.parse_args()
    socket_path = args.socket
    _ = args.no_open  # reserved for future use

    # Map subcommand to (cmd, args_dict)
    cmd_name = args.command
    cmd_args: dict = {}
    opens_browser = False

    if cmd_name in ("agent", "a"):
        cmd_name = "spawn-agent"
        cmd_args = {"role": args.role}
        if args.agent_id:
            cmd_args["agent_id"] = args.agent_id
        if args.nats_url:
            cmd_args["nats_url"] = args.nats_url
        if args.workspace:
            cmd_args["workspace"] = args.workspace

        if args.cmd:
            # Custom command override
            cmd_args["cmd"] = args.cmd
        elif args.teammate:
            # Open a shell with tmux shim env vars pre-set.
            socket_path_val = args.socket
            shim_bin = _find_tmux_shim_dir()

            # Build env export commands for the shell
            env_exports = (
                f"export TMUX={socket_path_val},{os.getpid()},0; "
                f"export TMUX_PANE=%0; "
                f"export WM_SOCKET={socket_path_val}; "
            )
            if shim_bin:
                env_exports += f"export PATH={shim_bin}:$PATH; "

            # Launch bash with env pre-set, print hint
            cmd_args["cmd"] = (
                f"bash -c '{env_exports} "
                f"echo \"=== tmux shim env ready ===\"; "
                f"echo \"  TMUX=$TMUX\"; "
                f"echo \"  WM_SOCKET=$WM_SOCKET\"; "
                f"echo \"  tmux shim: $(which tmux)\"; "
                f"echo \"\"; "
                f"echo \"Run: claude --teammate-mode tmux\"; "
                f"echo \"\"; "
                f"exec bash'"
            )
        elif args.nats:
            # NATS worker mode
            cmd_args["claude"] = args.claude
            if args.model:
                cmd_args["model"] = args.model
        else:
            # Default: interactive Claude in browser terminal
            claude_cmd = "claude"
            if args.model:
                claude_cmd += f" --model {args.model}"
            if args.system_prompt:
                claude_cmd += f" --system-prompt '{args.system_prompt}'"
            if args.dangerously_skip_permissions:
                claude_cmd += " --dangerously-skip-permissions"
            else:
                claude_cmd += f" --permission-mode {args.permission_mode}"
            claude_cmd += " --teammate-mode tmux"
            cmd_args["cmd"] = claude_cmd

        opens_browser = True
    elif cmd_name in ("list-windows", "lw"):
        cmd_name = "list-windows"
    elif cmd_name in ("new-window", "nw"):
        cmd_name = "new-window"
        cmd_args = {"title": args.title, "cmd": args.cmd}
        opens_browser = True
    elif cmd_name in ("split", "sp"):
        cmd_name = "split"
        cmd_args = {
            "direction": args.direction,
            "cmd": args.cmd,
            "title": args.title,
            "ratio": args.ratio,
        }
        if args.window_id:
            cmd_args["window_id"] = args.window_id
        if args.pane_id:
            cmd_args["target_pane"] = args.pane_id
        opens_browser = True
    elif cmd_name in ("close-window", "cw"):
        cmd_name = "close-window"
        cmd_args = {"window_id": args.window_id}
    elif cmd_name in ("close-pane", "cp"):
        cmd_name = "close-pane"
        cmd_args = {"pane_id": args.pane_id}
    elif cmd_name in ("focus", "f"):
        cmd_name = "focus"
        cmd_args = {"pane_id": args.pane_id}
    elif cmd_name in ("list-panes", "lp"):
        cmd_name = "list-panes"
        if args.window_id:
            cmd_args = {"window_id": args.window_id}
    elif cmd_name in ("layout", "lo"):
        cmd_name = "layout"
        if args.window_id:
            cmd_args = {"window_id": args.window_id}

    resp = asyncio.run(_send_command(socket_path, cmd_name, cmd_args))

    if not resp.get("ok"):
        print(f"Error: {resp.get('error', 'unknown')}", file=sys.stderr)
        sys.exit(1)

    data = resp.get("data", {})

    if opens_browser and isinstance(data, dict) and data.get("session_id"):
        _print_session(data)
    else:
        _print_result(resp)


if __name__ == "__main__":
    main()

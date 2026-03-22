"""tmux shim -- translates tmux CLI commands to WM socket operations.

Installed as `tmux-shim` and symlinked/aliased as `tmux` on PATH.
When Claude (--teammate-mode tmux) runs tmux commands, this shim
intercepts them and forwards to the TmuxSessionRegistry Unix socket.

Socket discovery (in order):
    1. WM_SOCKET env var
    2. TMUX env var (first comma-separated field)
    3. /tmp/aetherterm-wm-{uid}/default.sock

Supported subcommands:
    new-window, split-window, send-keys, capture-pane, list-panes,
    list-windows, select-pane, kill-pane, display-message, has-session
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from datetime import datetime


_LOG_PATH = os.environ.get("TMUX_SHIM_LOG", "/tmp/tmux-shim.log")


def _log(msg: str) -> None:
    try:
        with open(_LOG_PATH, "a") as f:
            f.write(f"{datetime.now().isoformat()} {msg}\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Socket discovery
# ---------------------------------------------------------------------------

def _find_socket_path() -> str:
    wm_sock = os.environ.get("WM_SOCKET")
    if wm_sock:
        return wm_sock
    tmux_env = os.environ.get("TMUX", "")
    if tmux_env:
        parts = tmux_env.split(",")
        if parts[0]:
            return parts[0]
    uid = os.getuid()
    return f"/tmp/aetherterm-wm-{uid}/default.sock"


# ---------------------------------------------------------------------------
# Socket communication (blocking — no asyncio)
# ---------------------------------------------------------------------------

def _send_sync(cmd: str, args: dict) -> dict:
    sock_path = _find_socket_path()
    _log(f"  -> socket send: cmd={cmd} args={json.dumps(args, ensure_ascii=False)[:300]}")
    resp = _send_plain(sock_path, cmd, args)
    _log(f"  <- socket recv: {json.dumps(resp, ensure_ascii=False)[:300]}")
    return resp


def _send_plain(socket_path: str, cmd: str, args: dict) -> dict:
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect(socket_path)
    except (ConnectionRefusedError, FileNotFoundError, OSError) as e:
        return {"ok": False, "error": f"Cannot connect to {socket_path}: {e}"}

    try:
        req = json.dumps({"cmd": cmd, "args": args}) + "\n"
        sock.sendall(req.encode())

        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk

        if not buf:
            return {"ok": False, "error": "No response"}
        return json.loads(buf.decode().strip())
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        sock.close()


# ---------------------------------------------------------------------------
# tmux format string helpers
# ---------------------------------------------------------------------------

def _format_pane(pane: dict, fmt: str) -> str:
    result = fmt
    result = result.replace("#{pane_id}", pane.get("pane_id", ""))
    result = result.replace("#{pane_title}", pane.get("title", ""))
    result = result.replace("#{pane_current_command}", pane.get("cmd", ""))
    result = result.replace("#{session_id}", pane.get("session_id", ""))
    result = result.replace("#{window_id}", pane.get("window_id", ""))
    result = result.replace("#{window_name}", pane.get("window_title", ""))
    result = result.replace("#{pane_active}", "1" if pane.get("focused") else "0")
    return result


def _format_window(win: dict, fmt: str) -> str:
    result = fmt
    result = result.replace("#{window_id}", win.get("window_id", ""))
    result = result.replace("#{window_name}", win.get("title", ""))
    result = result.replace("#{window_panes}", str(win.get("pane_count", 0)))
    result = result.replace("#{window_active}", "1" if win.get("active") else "0")
    return result


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_new_window(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="tmux new-window", add_help=False)
    p.add_argument("-n", dest="name", default="Shell")
    p.add_argument("-t", dest="target", default=None)
    p.add_argument("-d", dest="detach", action="store_true")
    p.add_argument("-P", dest="print_info", action="store_true")
    p.add_argument("-F", dest="format", default=None)
    args, remaining = p.parse_known_args(argv)

    shell_cmd = " ".join(remaining) if remaining else ""
    resp = _send_sync("new-window", {"title": args.name, "cmd": shell_cmd})
    if not resp.get("ok"):
        print(resp.get("error", "failed"), file=sys.stderr)
        return 1

    data = resp.get("data", {})
    if args.print_info:
        if args.format:
            print(_format_window(data, args.format))
        else:
            print(f"{data.get('window_id', '')}:{data.get('title', '')}")
    return 0


def cmd_split_window(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="tmux split-window", add_help=False)
    p.add_argument("-h", dest="horizontal", action="store_true")
    p.add_argument("-v", dest="vertical", action="store_true")
    p.add_argument("-t", dest="target", default=None)
    p.add_argument("-p", dest="percent", type=int, default=50)
    p.add_argument("-d", dest="detach", action="store_true")
    p.add_argument("-P", dest="print_info", action="store_true")
    p.add_argument("-F", dest="format", default=None)
    args, remaining = p.parse_known_args(argv)

    shell_cmd = " ".join(remaining) if remaining else ""
    direction = "v" if args.vertical else "h"

    cmd_args: dict = {"direction": direction, "cmd": shell_cmd}
    if args.target:
        cmd_args["target_pane"] = args.target

    resp = _send_sync("split", cmd_args)
    if not resp.get("ok"):
        print(resp.get("error", "split failed"), file=sys.stderr)
        return 1

    data = resp.get("data", {})
    if args.print_info:
        if args.format:
            print(_format_pane(data, args.format))
        else:
            print(data.get("pane_id", ""))
    return 0


def cmd_send_keys(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="tmux send-keys", add_help=False)
    p.add_argument("-t", dest="target", default=None)
    p.add_argument("-l", dest="literal", action="store_true")
    args, remaining = p.parse_known_args(argv)

    keys = []
    for k in remaining:
        if k == "Enter":
            keys.append("\n")
        elif k == "Escape":
            keys.append("\x1b")
        elif k == "Tab":
            keys.append("\t")
        elif k == "Space":
            keys.append(" ")
        elif k == "BSpace":
            keys.append("\x7f")
        elif k.startswith("C-") and len(k) == 3:
            keys.append(chr(ord(k[2].upper()) - 64))
        else:
            keys.append(k)

    text = "".join(keys)
    cmd_args: dict = {"keys": text}
    if args.target:
        cmd_args["pane_id"] = args.target

    resp = _send_sync("send-keys", cmd_args)
    if not resp.get("ok"):
        print(resp.get("error", "send-keys failed"), file=sys.stderr)
        return 1
    return 0


def cmd_capture_pane(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="tmux capture-pane", add_help=False)
    p.add_argument("-t", dest="target", default=None)
    p.add_argument("-p", dest="print_mode", action="store_true")
    p.add_argument("-S", dest="start_line", default=None)
    p.add_argument("-E", dest="end_line", default=None)
    p.add_argument("-J", dest="join", action="store_true")
    p.add_argument("-e", dest="escape", action="store_true")
    args, _ = p.parse_known_args(argv)

    cmd_args: dict = {}
    if args.target:
        cmd_args["pane_id"] = args.target

    resp = _send_sync("capture-pane", cmd_args)
    if not resp.get("ok"):
        print(resp.get("error", "capture-pane failed"), file=sys.stderr)
        return 1

    if args.print_mode:
        content = resp.get("data", {}).get("content", "")
        if content:
            print(content)
    return 0


def cmd_list_panes(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="tmux list-panes", add_help=False)
    p.add_argument("-a", dest="all", action="store_true")
    p.add_argument("-t", dest="target", default=None)
    p.add_argument("-F", dest="format", default=None)
    args, _ = p.parse_known_args(argv)

    cmd_args: dict = {}
    if args.target and not args.all:
        cmd_args["window_id"] = args.target

    resp = _send_sync("list-panes", cmd_args)
    if not resp.get("ok"):
        print(resp.get("error", "failed"), file=sys.stderr)
        return 1

    for pane in resp.get("data", []):
        if args.format:
            print(_format_pane(pane, args.format))
        else:
            active = "*" if pane.get("focused") else " "
            print(f"{pane.get('pane_id', '')}: [{pane.get('title', '')}] {active}")
    return 0


def cmd_list_windows(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="tmux list-windows", add_help=False)
    p.add_argument("-t", dest="target", default=None)
    p.add_argument("-F", dest="format", default=None)
    args, _ = p.parse_known_args(argv)

    resp = _send_sync("list-windows", {})
    if not resp.get("ok"):
        print(resp.get("error", "failed"), file=sys.stderr)
        return 1

    for win in resp.get("data", []):
        if args.format:
            print(_format_window(win, args.format))
        else:
            active = "*" if win.get("active") else " "
            wid = win.get('window_id', '')
            title = win.get('title', '')
            panes = win.get('pane_count', 0)
            print(f"{wid}: {title} ({panes} panes) {active}")
    return 0


def cmd_select_pane(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="tmux select-pane", add_help=False)
    p.add_argument("-t", dest="target", default=None)
    args, _ = p.parse_known_args(argv)

    if not args.target:
        print("target required", file=sys.stderr)
        return 1

    resp = _send_sync("focus", {"pane_id": args.target})
    if not resp.get("ok"):
        print(resp.get("error", "failed"), file=sys.stderr)
        return 1
    return 0


def cmd_kill_pane(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="tmux kill-pane", add_help=False)
    p.add_argument("-t", dest="target", default=None)
    args, _ = p.parse_known_args(argv)

    if not args.target:
        print("target required", file=sys.stderr)
        return 1

    resp = _send_sync("close-pane", {"pane_id": args.target})
    if not resp.get("ok"):
        print(resp.get("error", "failed"), file=sys.stderr)
        return 1
    return 0


def cmd_display_message(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="tmux display-message", add_help=False)
    p.add_argument("-p", dest="print_mode", action="store_true")
    p.add_argument("-t", dest="target", default=None)
    args, remaining = p.parse_known_args(argv)

    fmt = " ".join(remaining) if remaining else "#{session_name}"

    if "pane_id" in fmt or "pane_" in fmt:
        resp = _send_sync("list-panes", {})
        panes = resp.get("data", []) if resp.get("ok") else []
        if panes:
            target = panes[0]
            if args.target:
                for p_item in panes:
                    if p_item.get("pane_id") == args.target:
                        target = p_item
                        break
            print(_format_pane(target, fmt))
    elif "window_" in fmt:
        resp = _send_sync("list-windows", {})
        windows = resp.get("data", []) if resp.get("ok") else []
        if windows:
            print(_format_window(windows[0], fmt))
    else:
        print(fmt.replace("#{session_name}", "aetherterm"))
    return 0


def cmd_has_session(argv: list[str]) -> int:
    return 0


def cmd_list_sessions(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="tmux list-sessions", add_help=False)
    p.add_argument("-F", dest="format", default=None)
    args, _ = p.parse_known_args(argv)

    session_name = "aetherterm"
    if args.format:
        result = args.format
        result = result.replace("#{session_name}", session_name)
        result = result.replace("#{session_id}", "$0")
        result = result.replace("#{session_windows}", "1")
        result = result.replace("#{session_attached}", "1")
        result = result.replace("#{session_created}", "0")
        print(result)
    else:
        print(f"{session_name}: 1 windows (created) [80x24] (attached)")
    return 0


def cmd_server_info(argv: list[str]) -> int:
    print("tmux-shim (aetherterm-backed)")
    return 0


SUBCOMMANDS = {
    "new-window": cmd_new_window,
    "split-window": cmd_split_window,
    "send-keys": cmd_send_keys,
    "capture-pane": cmd_capture_pane,
    "list-panes": cmd_list_panes,
    "list-windows": cmd_list_windows,
    "select-pane": cmd_select_pane,
    "kill-pane": cmd_kill_pane,
    "kill-window": lambda argv: (
        _send_sync("close-window", {"window_id": argv[0] if argv else ""}) or 0
    ),
    "display-message": cmd_display_message,
    "has-session": cmd_has_session,
    "list-sessions": cmd_list_sessions,
    "server-info": cmd_server_info,
    "info": cmd_server_info,
    # Aliases
    "neww": cmd_new_window,
    "splitw": cmd_split_window,
    "split-pane": cmd_split_window,
    "send": cmd_send_keys,
    "capturep": cmd_capture_pane,
    "lsp": cmd_list_panes,
    "lsw": cmd_list_windows,
    "ls": cmd_list_sessions,
    "list-session": cmd_list_sessions,
    "selectp": cmd_select_pane,
    "killp": cmd_kill_pane,
    "killw": lambda argv: (
        _send_sync("close-window", {"window_id": argv[0] if argv else ""}) or 0
    ),
    "display": cmd_display_message,
    "has": cmd_has_session,
}


def main():
    argv = sys.argv[1:]

    while argv and argv[0].startswith("-"):
        flag = argv.pop(0)
        if flag in ("-V", "--version"):
            print("tmux 3.4 (tmux-shim/aetherterm)")
            return 0
        if flag in ("-S", "-L", "-f") and argv:
            argv.pop(0)

    if not argv:
        print("tmux-shim: aetherterm-backed tmux shim")
        print("Socket:", _find_socket_path())
        return 0

    subcmd = argv[0]
    subcmd_argv = argv[1:]

    _log(f"cmd: tmux {subcmd} {' '.join(subcmd_argv)}")

    handler = SUBCOMMANDS.get(subcmd)
    if handler is None:
        print(f"tmux-shim: unsupported subcommand '{subcmd}'", file=sys.stderr)
        return 1

    return handler(subcmd_argv)


if __name__ == "__main__":
    sys.exit(main())

"""AetherTerm tmux-compatible CLI.

Talks to the AgentServer REST API to manage tmux sessions, windows, and panes.

Usage:
    aetherterm-tmux list-sessions
    aetherterm-tmux new-session -n my-session
    aetherterm-tmux send-keys -t pane_abc123 ls Enter
    aetherterm-tmux project-setup --spec plan.json
"""

import json
import sys

import click
import httpx


@click.group()
@click.option(
    "--server",
    "-s",
    default="http://localhost:57575",
    envvar="AETHERTERM_SERVER",
    help="AgentServer URL",
)
@click.pass_context
def tmux(ctx, server):
    """AetherTerm tmux-compatible CLI."""
    ctx.ensure_object(dict)
    ctx.obj["server"] = server.rstrip("/")
    ctx.obj["client"] = httpx.Client(base_url=server.rstrip("/"), timeout=10.0)


def _client(ctx) -> httpx.Client:
    return ctx.obj["client"]


def _api(ctx, method: str, path: str, **kwargs):
    """Make an API call and handle errors."""
    try:
        r = getattr(_client(ctx), method)(f"/api/tmux{path}", **kwargs)
        if r.status_code >= 400:
            detail = r.json().get("detail", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
            click.echo(f"Error ({r.status_code}): {detail}", err=True)
            sys.exit(1)
        return r.json()
    except httpx.ConnectError:
        click.echo(f"Error: Cannot connect to {ctx.obj['server']}", err=True)
        sys.exit(1)


# --- Special key mapping ---

SPECIAL_KEYS = {
    "Enter": "\n",
    "C-c": "\x03",
    "C-d": "\x04",
    "C-z": "\x1a",
    "C-l": "\x0c",
    "C-a": "\x01",
    "C-e": "\x05",
    "C-k": "\x0b",
    "C-u": "\x15",
    "C-w": "\x17",
    "Escape": "\x1b",
    "Tab": "\t",
    "Space": " ",
    "BSpace": "\x7f",
}


def _resolve_keys(keys: tuple[str, ...]) -> str:
    """Resolve a sequence of key arguments into a single string."""
    parts = []
    for key in keys:
        parts.append(SPECIAL_KEYS.get(key, key))
    return "".join(parts)


# --- Session Commands ---


@tmux.command("list-sessions")
@click.pass_context
def list_sessions(ctx):
    """List all tmux sessions."""
    sessions = _api(ctx, "get", "/sessions")
    if not sessions:
        click.echo("No sessions.")
        return
    for s in sessions:
        windows = s.get("windows", {})
        click.echo(f"{s['session_id']}: {s['name']} ({len(windows)} windows)")


@tmux.command("new-session")
@click.option("-n", "--name", default="", help="Session name")
@click.pass_context
def new_session(ctx, name):
    """Create a new session."""
    result = _api(ctx, "post", "/sessions", json={"name": name})
    click.echo(f"Created session: {result['session_id']} ({result['name']})")


@tmux.command("kill-session")
@click.option("-t", "--target", required=True, help="Session ID")
@click.pass_context
def kill_session(ctx, target):
    """Destroy a session."""
    _api(ctx, "delete", f"/sessions/{target}")
    click.echo(f"Killed session: {target}")


@tmux.command("rename-session")
@click.option("-t", "--target", required=True, help="Session ID")
@click.argument("name")
@click.pass_context
def rename_session(ctx, target, name):
    """Rename a session."""
    result = _api(ctx, "put", f"/sessions/{target}", json={"name": name})
    click.echo(f"Renamed session {target} → {result['name']}")


@tmux.command("show-session")
@click.option("-t", "--target", required=True, help="Session ID")
@click.pass_context
def show_session(ctx, target):
    """Show session details."""
    result = _api(ctx, "get", f"/sessions/{target}")
    click.echo(f"Session: {result['session_id']} ({result['name']})")
    click.echo(f"  Active window: {result.get('active_window_id', 'none')}")
    click.echo(f"  Clients: {result.get('active_clients', 0)}")
    for wid, w in result.get("windows", {}).items():
        panes = w.get("panes", {})
        click.echo(f"  Window {wid} ({w['name']}): {len(panes)} panes")


# --- Window Commands ---


@tmux.command("new-window")
@click.option("-t", "--target", required=True, help="Session ID")
@click.option("-n", "--name", default="", help="Window name")
@click.pass_context
def new_window(ctx, target, name):
    """Create a new window in a session."""
    result = _api(ctx, "post", f"/sessions/{target}/windows", json={"name": name})
    click.echo(f"Created window: {result['window_id']} ({result['name']})")


@tmux.command("kill-window")
@click.option("-t", "--target", required=True, help="session_id:window_id")
@click.pass_context
def kill_window(ctx, target):
    """Close a window."""
    session_id, window_id = _parse_target(target, "session_id:window_id")
    _api(ctx, "delete", f"/sessions/{session_id}/windows/{window_id}")
    click.echo(f"Closed window: {window_id}")


@tmux.command("select-window")
@click.option("-t", "--target", required=True, help="session_id:window_id")
@click.pass_context
def select_window(ctx, target):
    """Select the active window."""
    session_id, window_id = _parse_target(target, "session_id:window_id")
    _api(ctx, "post", f"/sessions/{session_id}/windows/{window_id}/select")
    click.echo(f"Selected window: {window_id}")


@tmux.command("rename-window")
@click.option("-t", "--target", required=True, help="session_id:window_id")
@click.argument("name")
@click.pass_context
def rename_window(ctx, target, name):
    """Rename a window."""
    session_id, window_id = _parse_target(target, "session_id:window_id")
    result = _api(ctx, "put", f"/sessions/{session_id}/windows/{window_id}", json={"name": name})
    click.echo(f"Renamed window {window_id} → {result['name']}")


# --- Pane Commands ---


@tmux.command("list-panes")
@click.option("-t", "--target", required=True, help="Session ID")
@click.pass_context
def list_panes(ctx, target):
    """List all panes in a session."""
    panes = _api(ctx, "get", f"/sessions/{target}/panes")
    if not panes:
        click.echo("No panes.")
        return
    for p in panes:
        role = f" [{p['role']}]" if p.get("role") else ""
        click.echo(
            f"  {p['pane_id']} ({p['status']}) {p['cols']}x{p['rows']}"
            f" win={p.get('window_id', '?')}{role}"
        )


@tmux.command("split-window")
@click.option("-t", "--target", required=True, help="Session ID")
@click.option("-v", "--vertical", "direction", flag_value="v", default=True, help="Vertical split")
@click.option("-h", "--horizontal", "direction", flag_value="h", help="Horizontal split")
@click.option("--pane", default="", help="Target pane ID to split")
@click.pass_context
def split_window(ctx, target, direction, pane):
    """Split a pane in the session."""
    body = {"direction": direction}
    if pane:
        body["pane_id"] = pane
    result = _api(ctx, "post", f"/sessions/{target}/panes/split", json=body)
    click.echo(f"Created pane: {result['pane_id']} (split {direction})")


@tmux.command("kill-pane")
@click.option("-t", "--target", required=True, help="session_id:pane_id")
@click.pass_context
def kill_pane(ctx, target):
    """Close a pane."""
    session_id, pane_id = _parse_target(target, "session_id:pane_id")
    _api(ctx, "delete", f"/sessions/{session_id}/panes/{pane_id}")
    click.echo(f"Closed pane: {pane_id}")


@tmux.command("select-pane")
@click.option("-t", "--target", required=True, help="session_id:pane_id")
@click.pass_context
def select_pane(ctx, target):
    """Focus a pane."""
    session_id, pane_id = _parse_target(target, "session_id:pane_id")
    _api(ctx, "post", f"/sessions/{session_id}/panes/{pane_id}/focus")
    click.echo(f"Focused pane: {pane_id}")


@tmux.command("send-keys")
@click.option("-t", "--target", required=True, help="session_id:pane_id")
@click.argument("keys", nargs=-1)
@click.pass_context
def send_keys(ctx, target, keys):
    """Send keys to a pane. Use 'Enter' for newline, 'C-c' for Ctrl+C."""
    if not keys:
        click.echo("No keys specified.", err=True)
        sys.exit(1)
    session_id, pane_id = _parse_target(target, "session_id:pane_id")
    data = _resolve_keys(keys)
    _api(ctx, "post", f"/sessions/{session_id}/panes/{pane_id}/send-keys", json={"data": data})
    click.echo(f"Sent {len(keys)} key(s) to {pane_id}")


@tmux.command("capture-pane")
@click.option("-t", "--target", required=True, help="session_id:pane_id")
@click.option("-p", "--print", "do_print", is_flag=True, help="Print to stdout")
@click.option("--lines", "-l", default=100, help="Number of lines to capture")
@click.pass_context
def capture_pane(ctx, target, do_print, lines):
    """Capture pane scrollback content."""
    session_id, pane_id = _parse_target(target, "session_id:pane_id")
    result = _api(ctx, "get", f"/sessions/{session_id}/panes/{pane_id}/capture?lines={lines}")
    captured_lines = result.get("lines", [])
    if do_print:
        for line in captured_lines:
            click.echo(line)
    else:
        click.echo(f"Captured {len(captured_lines)} lines from {pane_id}")


@tmux.command("resize-pane")
@click.option("-t", "--target", required=True, help="session_id:pane_id")
@click.option("-x", "--width", type=int, help="Columns")
@click.option("-y", "--height", type=int, help="Rows")
@click.pass_context
def resize_pane(ctx, target, width, height):
    """Resize a pane's PTY dimensions."""
    if width is None and height is None:
        click.echo("Specify at least one of --width or --height", err=True)
        sys.exit(1)
    session_id, pane_id = _parse_target(target, "session_id:pane_id")
    # Get current dimensions first if one is missing
    if width is None or height is None:
        panes = _api(ctx, "get", f"/sessions/{session_id}/panes")
        current = next((p for p in panes if p["pane_id"] == pane_id), None)
        if current is None:
            click.echo(f"Pane {pane_id} not found", err=True)
            sys.exit(1)
        if width is None:
            width = current["cols"]
        if height is None:
            height = current["rows"]
    _api(
        ctx,
        "post",
        f"/sessions/{session_id}/panes/{pane_id}/resize",
        json={"cols": width, "rows": height},
    )
    click.echo(f"Resized {pane_id} to {width}x{height}")


# --- Layout Commands ---


@tmux.command("apply-layout")
@click.option("-t", "--target", required=True, help="session_id:window_id")
@click.argument("preset")
@click.pass_context
def apply_layout(ctx, target, preset):
    """Apply a preset layout to a window."""
    session_id, window_id = _parse_target(target, "session_id:window_id")
    _api(
        ctx,
        "post",
        f"/sessions/{session_id}/windows/{window_id}/layout",
        json={"preset": preset},
    )
    click.echo(f"Applied layout '{preset}' to {window_id}")


# --- Project Setup ---


@tmux.command("project-setup")
@click.option(
    "--spec",
    required=True,
    type=click.Path(exists=False),
    help="Path to JSON spec file, or '-' for stdin",
)
@click.option("--session", default="", help="Existing session ID to add windows to")
@click.pass_context
def project_setup(ctx, spec, session):
    """Create a full project workspace (session → windows → panes) from a JSON spec."""
    # Read spec from file or stdin
    if spec == "-":
        raw = sys.stdin.read()
    else:
        try:
            with open(spec) as f:
                raw = f.read()
        except FileNotFoundError:
            click.echo(f"Error: File not found: {spec}", err=True)
            sys.exit(1)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        click.echo(f"Error: Invalid JSON: {e}", err=True)
        sys.exit(1)

    # Override session_id if --session is provided
    if session:
        payload["session_id"] = session
        payload.pop("session_name", None)

    result = _api(ctx, "post", "/project-setup", json=payload)

    click.echo(f"Session: {result['session_id']} ({result.get('session_name', '')})")
    for w in result.get("windows", []):
        panes = w.get("panes", [])
        click.echo(f"  Window {w['window_id']} ({w['name']}): {len(panes)} pane(s)")
        for pid in panes:
            click.echo(f"    - {pid}")


# --- Utilities ---


def _parse_target(target: str, expected: str) -> tuple[str, str]:
    """Parse a colon-separated target like 'session_id:window_id'."""
    parts = target.split(":", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        click.echo(f"Invalid target format: {target!r} (expected {expected})", err=True)
        sys.exit(1)
    return parts[0], parts[1]


if __name__ == "__main__":
    tmux()

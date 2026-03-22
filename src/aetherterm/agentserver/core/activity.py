"""Activity log and event hub for timeline tracking.

Provides:
- ActivityLog: In-memory timeline of agent interactions
- EventHub: WebSocket push to connected browsers (state change broadcast)
- Session-scoped activity logs via get_session_log()
- Timeline summarization (Claude API with rule-based fallback)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from starlette.websockets import WebSocketState
from fastapi import WebSocket

log = logging.getLogger("aetherterm.activity")


# ---------------------------------------------------------------------------
# Activity Log
# ---------------------------------------------------------------------------

class ActivityLog:
    """In-memory log of orchestrator <-> agent interactions for timeline view."""

    def __init__(self, max_entries: int = 500):
        self._entries: list[dict] = []
        self._max = max_entries
        self._counter = 0

    def add(
        self,
        event_type: str,
        source: str = "",
        target: str = "",
        detail: str = "",
        meta: dict | None = None,
    ) -> dict:
        self._counter += 1
        entry = {
            "id": self._counter,
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "source": source,
            "target": target,
            "detail": detail,
        }
        if meta:
            entry["meta"] = meta
        self._entries.append(entry)
        if len(self._entries) > self._max:
            self._entries = self._entries[-self._max:]
        return entry

    def entries(self, since_id: int = 0, limit: int = 200) -> list[dict]:
        if since_id:
            return [e for e in self._entries if e["id"] > since_id][-limit:]
        return self._entries[-limit:]


# Session-scoped activity logs
_session_logs: dict[str, ActivityLog] = {}


def get_session_log(session_name: str = "default") -> ActivityLog:
    """Get or create a session-scoped activity log."""
    if session_name not in _session_logs:
        _session_logs[session_name] = ActivityLog()
    return _session_logs[session_name]


# ---------------------------------------------------------------------------
# Event Hub
# ---------------------------------------------------------------------------

class EventHub:
    """Broadcasts events to connected workspace browsers via WebSocket."""

    def __init__(self):
        self._clients: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.append(ws)
        log.debug("EventHub: client connected (%d total)", len(self._clients))

    def disconnect(self, ws: WebSocket) -> None:
        self._clients = [c for c in self._clients if c is not ws]
        log.debug("EventHub: client disconnected (%d total)", len(self._clients))

    async def broadcast(self, event: dict) -> None:
        data = json.dumps(event)
        dead = []
        for ws in self._clients:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def notify_state_change(
        self, session_id: str, event_type: str, detail: dict | None = None,
    ) -> None:
        await self.broadcast({
            "type": event_type,
            "session_id": session_id,
            **(detail or {}),
        })


_event_hub = EventHub()


def get_event_hub() -> EventHub:
    return _event_hub


# ---------------------------------------------------------------------------
# Timeline summarization
# ---------------------------------------------------------------------------

async def summarize_timeline(entries: list[dict]) -> dict:
    """Summarize timeline entries using Claude API."""
    try:
        import anthropic
    except ImportError:
        return _rule_based_summary(entries)

    lines = []
    for e in entries:
        ts = e.get("ts", "")[:19]
        src = e.get('source', '')
        tgt = e.get('target', '')
        det = e.get('detail', '')
        lines.append(f"[{ts}] {e['type']}: {src} -> {tgt} {det}")
    text = "\n".join(lines)

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": (
                    "Summarize this multi-agent system timeline "
                    "concisely in Japanese. Focus on key events "
                    "(task creation, completion, errors, "
                    "agent communication).\n\n"
                    f"{text}"
                ),
            }],
        )
        return {"summary": response.content[0].text}
    except Exception as e:
        log.warning("Claude API summarization failed: %s, falling back to rule-based", e)
        return _rule_based_summary(entries)


def _rule_based_summary(entries: list[dict]) -> dict:
    """Simple rule-based summary when Claude API is unavailable."""
    counts: dict[str, int] = {}
    agents: set[str] = set()
    for e in entries:
        t = e.get("type", "unknown")
        counts[t] = counts.get(t, 0) + 1
        if e.get("source"):
            agents.add(e["source"])
        if e.get("target"):
            agents.add(e["target"])
    agents.discard("")
    agents.discard("ui")

    lines = [f"Total events: {len(entries)}"]
    if agents:
        lines.append(f"Agents: {', '.join(sorted(agents))}")
    for t, c in sorted(counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {t}: {c}")

    tasks_created = sum(1 for e in entries if e["type"] == "task_create")
    tasks_done = sum(1 for e in entries if e["type"] == "task_complete")
    dms = sum(1 for e in entries if e["type"] == "agent_dm")

    if tasks_created:
        lines.append(f"\nTasks created: {tasks_created}")
    if tasks_done:
        lines.append(f"Tasks completed: {tasks_done}")
    if dms:
        lines.append(f"Agent DMs: {dms}")

    return {"summary": "\n".join(lines)}

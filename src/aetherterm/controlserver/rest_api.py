"""REST API -- Extracted from CentralController.

Provides admin REST endpoints for ControlServer management.
Includes health/readiness probes, metrics, agent health, and all
existing session/block/analysis endpoints.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from .central_controller import CentralController

logger = logging.getLogger(__name__)


def create_rest_app(controller: CentralController) -> FastAPI:
    """Create the FastAPI REST application for ControlServer admin."""
    app = FastAPI(
        title="ControlServer Admin API",
        version="0.2.0",
        description="AetherTerm ControlServer management and monitoring API",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Store controller reference for dependency injection
    app.state.controller = controller

    def get_controller() -> CentralController:
        return app.state.controller

    # ------------------------------------------------------------------
    # Health & Readiness probes (for Kubernetes)
    # ------------------------------------------------------------------

    @app.get("/healthz", tags=["health"])
    async def healthz():
        """Liveness probe: returns 200 if the process is alive."""
        return {"status": "ok"}

    @app.get("/readyz", tags=["health"])
    async def readyz(ctrl: CentralController = Depends(get_controller)):
        """Readiness probe: returns 200 if the server is ready to accept traffic."""
        nats_ok = ctrl._nats_controller is not None and ctrl._nats_controller.is_connected
        ws_ok = ctrl.server is not None

        ready = nats_ok or ws_ok
        status_code = 200 if ready else 503

        return JSONResponse(
            status_code=status_code,
            content={
                "status": "ready" if ready else "not_ready",
                "nats_connected": nats_ok,
                "websocket_server": ws_ok,
            },
        )

    # ------------------------------------------------------------------
    # Status & Metrics
    # ------------------------------------------------------------------

    @app.get("/api/status", tags=["status"])
    async def api_status(ctrl: CentralController = Depends(get_controller)):
        return JSONResponse(ctrl.get_status_summary())

    @app.get("/api/metrics", tags=["metrics"])
    async def api_metrics(ctrl: CentralController = Depends(get_controller)):
        """Current system metrics snapshot."""
        if ctrl._metrics_collector:
            latest = ctrl._metrics_collector.get_latest()
            if latest:
                return JSONResponse(latest)
            # Collect on-demand if no history yet
            snap = ctrl._metrics_collector.collect_now()
            return JSONResponse(snap.to_dict())
        return JSONResponse({"error": "metrics collector not available"}, status_code=503)

    @app.get("/api/metrics/history", tags=["metrics"])
    async def api_metrics_history(
        count: int = 20,
        ctrl: CentralController = Depends(get_controller),
    ):
        """Historical metrics (default last 20 snapshots)."""
        if ctrl._metrics_collector:
            return JSONResponse(ctrl._metrics_collector.get_history(count))
        return JSONResponse([])

    # ------------------------------------------------------------------
    # Agent Health
    # ------------------------------------------------------------------

    @app.get("/api/agents/health", tags=["agents"])
    async def api_agents_health(ctrl: CentralController = Depends(get_controller)):
        """Health status of all connected agents."""
        if ctrl._health_monitor:
            return JSONResponse(ctrl._health_monitor.get_all_health())
        return JSONResponse([])

    @app.get("/api/agents/{agent_id}/health", tags=["agents"])
    async def api_agent_health(
        agent_id: str,
        ctrl: CentralController = Depends(get_controller),
    ):
        """Health status of a specific agent."""
        if ctrl._health_monitor:
            health = ctrl._health_monitor.get_health(agent_id)
            if health:
                return JSONResponse(health)
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    @app.get("/api/sessions", tags=["sessions"])
    async def api_sessions(ctrl: CentralController = Depends(get_controller)):
        if ctrl._nats_controller:
            sessions = ctrl._nats_controller.list_sessions()
            return JSONResponse([
                {
                    "session_id": s.session_id,
                    "agent_server_id": s.agent_server_id,
                    "pane_ids": s.pane_ids,
                    "shell_ids": s.shell_ids,
                    "age_seconds": round(s.age_seconds, 1),
                }
                for s in sessions
            ])
        return JSONResponse([
            s.model_dump() for s in ctrl.active_sessions.values()
        ])

    @app.get("/api/shells", tags=["sessions"])
    async def api_shells(ctrl: CentralController = Depends(get_controller)):
        if ctrl._nats_controller:
            shells = ctrl._nats_controller.list_shells()
            return JSONResponse([
                {
                    "shell_id": s.shell_id,
                    "session_id": s.session_id,
                    "agent_server_id": s.agent_server_id,
                }
                for s in shells
            ])
        return JSONResponse([])

    # ------------------------------------------------------------------
    # Session Control
    # ------------------------------------------------------------------

    @app.post("/api/sessions/{session_id}/block", tags=["control"])
    async def api_block_session(
        session_id: str,
        request: Request,
        ctrl: CentralController = Depends(get_controller),
    ):
        body: dict[str, Any] = {}
        if request.headers.get("content-type", "").startswith("application/json"):
            body = await request.json()

        reason = body.get("reason", "Admin-initiated block via REST API")

        if ctrl._nats_controller:
            await ctrl._nats_controller.send_block_input(
                session_id=session_id, reason=reason
            )

        await ctrl.execute_block_session({
            "session_id": session_id,
            "reason": reason,
            "admin_user": body.get("admin_user", "rest_api"),
        })
        return JSONResponse({"status": "blocked", "session_id": session_id})

    @app.post("/api/sessions/{session_id}/unblock", tags=["control"])
    async def api_unblock_session(
        session_id: str,
        request: Request,
        ctrl: CentralController = Depends(get_controller),
    ):
        body: dict[str, Any] = {}
        if request.headers.get("content-type", "").startswith("application/json"):
            body = await request.json()

        if ctrl._nats_controller:
            await ctrl._nats_controller.send_unblock_input(
                session_id=session_id,
                admin_user=body.get("admin_user", "rest_api"),
            )

        await ctrl.execute_unblock_session({
            "session_id": session_id,
            "admin_user": body.get("admin_user", "rest_api"),
        })
        return JSONResponse({"status": "unblocked", "session_id": session_id})

    @app.post("/api/sessions/{session_id}/kill", tags=["control"])
    async def api_kill_session(
        session_id: str,
        ctrl: CentralController = Depends(get_controller),
    ):
        if ctrl._nats_controller:
            info = ctrl._nats_controller.get_session(session_id)
            if info:
                await ctrl._nats_controller.send_to_agent(
                    info.agent_server_id,
                    "kill_session",
                    {"session_id": session_id},
                )
                return JSONResponse({"status": "kill_sent", "session_id": session_id})

        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # ------------------------------------------------------------------
    # Emergency
    # ------------------------------------------------------------------

    @app.post("/api/emergency-stop", tags=["control"])
    async def api_emergency_stop(
        request: Request,
        ctrl: CentralController = Depends(get_controller),
    ):
        body: dict[str, Any] = {}
        if request.headers.get("content-type", "").startswith("application/json"):
            body = await request.json()

        reason = body.get("reason", "Emergency stop via REST API")

        if ctrl._nats_controller:
            await ctrl._nats_controller.send_emergency_stop(reason=reason)

        await ctrl.execute_block_all({
            "reason": reason,
            "admin_user": body.get("admin_user", "rest_api"),
        })
        return JSONResponse({"status": "emergency_stop_triggered"})

    # ------------------------------------------------------------------
    # Log Analysis
    # ------------------------------------------------------------------

    @app.get("/api/analysis/{session_id}", tags=["analysis"])
    async def api_analysis_history(
        session_id: str,
        ctrl: CentralController = Depends(get_controller),
    ):
        history = ctrl._analysis_history.get(session_id, [])
        return JSONResponse([
            {
                "analysis_type": r.analysis_type,
                "anomalies": r.anomalies,
                "summary": r.summary,
                "risk_level": r.risk_level,
                "timestamp": r.timestamp,
                "model_used": r.model_used,
                "token_usage": r.token_usage,
            }
            for r in history
        ])

    # ------------------------------------------------------------------
    # Blocks
    # ------------------------------------------------------------------

    @app.get("/api/blocks", tags=["blocks"])
    async def api_active_blocks(ctrl: CentralController = Depends(get_controller)):
        return JSONResponse([b.model_dump() for b in ctrl.active_blocks.values()])

    @app.get("/api/blocks/history", tags=["blocks"])
    async def api_block_history(ctrl: CentralController = Depends(get_controller)):
        return JSONResponse([b.model_dump() for b in ctrl.block_history[-50:]])

    # ------------------------------------------------------------------
    # Topology: AgentServer -> User -> Session -> Pane (tree)
    # ------------------------------------------------------------------

    @app.get("/api/topology", tags=["topology"])
    async def api_topology(ctrl: CentralController = Depends(get_controller)):
        """Hierarchical view: AgentServer -> User -> Session -> Pane."""
        return JSONResponse(_build_topology(ctrl))

    @app.get("/api/topology/flat", tags=["topology"])
    async def api_topology_flat(ctrl: CentralController = Depends(get_controller)):
        """Flat rows for DataGrid: one row per pane with parent info."""
        return JSONResponse(_build_topology_flat(ctrl))

    # ------------------------------------------------------------------
    # Admin UI page
    # ------------------------------------------------------------------

    @app.get("/admin", tags=["admin"], include_in_schema=False)
    async def admin_page():
        """Serve the admin DataGrid page."""
        from fastapi.responses import HTMLResponse
        return HTMLResponse(_ADMIN_HTML)

    return app


# ---------------------------------------------------------------------------
# Topology builders
# ---------------------------------------------------------------------------


def _build_topology(ctrl: CentralController) -> list:
    """Build hierarchical AgentServer -> User -> Session -> Pane tree."""
    # Collect all sessions from NATS controller or legacy
    sessions_by_agent: dict[str, list] = {}

    if ctrl._nats_controller:
        for info in ctrl._nats_controller.list_sessions():
            agent_id = info.agent_server_id
            sessions_by_agent.setdefault(agent_id, []).append(info)
    else:
        for info in ctrl.active_sessions.values():
            agent_id = info.agent_server_id
            sessions_by_agent.setdefault(agent_id, []).append(info)

    # Also include agents with no sessions (from health monitor)
    if ctrl._health_monitor:
        for h in ctrl._health_monitor.get_all_health():
            aid = h["agent_id"]
            if aid not in sessions_by_agent:
                sessions_by_agent[aid] = []

    result = []
    for agent_id, sessions in sorted(sessions_by_agent.items()):
        # Group sessions by user
        users_map: dict[str, list] = {}
        for sess in sessions:
            user_key = _extract_user_key(sess)
            users_map.setdefault(user_key, []).append(sess)

        users = []
        for user_key, user_sessions in sorted(users_map.items()):
            sess_list = []
            for sess in user_sessions:
                sess_list.append(_session_to_dict(sess, ctrl))
            users.append({
                "user_id": user_key,
                "user_info": _extract_user_info(user_sessions[0]),
                "session_count": len(user_sessions),
                "pane_count": sum(len(s.get("panes", [])) for s in sess_list),
                "sessions": sess_list,
            })

        agent_health = None
        if ctrl._health_monitor:
            agent_health = ctrl._health_monitor.get_health(agent_id)

        result.append({
            "agent_server_id": agent_id,
            "health": agent_health,
            "user_count": len(users),
            "session_count": sum(u["session_count"] for u in users),
            "pane_count": sum(u["pane_count"] for u in users),
            "users": users,
        })

    return result


def _build_topology_flat(ctrl: CentralController) -> list:
    """Build flat rows for DataGrid: one row per pane."""
    rows = []
    topology = _build_topology(ctrl)

    for agent in topology:
        agent_id = agent["agent_server_id"]
        agent_healthy = (
            agent["health"]["is_healthy"] if agent.get("health") else None
        )

        for user in agent.get("users", []):
            user_id = user["user_id"]

            for sess in user.get("sessions", []):
                session_id = sess["session_id"]
                session_name = sess.get("name", "")
                is_blocked = sess.get("is_blocked", False)

                panes = sess.get("panes", [])
                if not panes:
                    # Session with no panes — still show a row
                    rows.append({
                        "agent_server_id": agent_id,
                        "agent_healthy": agent_healthy,
                        "user_id": user_id,
                        "session_id": session_id,
                        "session_name": session_name,
                        "is_blocked": is_blocked,
                        "pane_id": "",
                        "pane_status": "",
                        "pane_role": "",
                        "pane_title": "",
                    })
                else:
                    for pane in panes:
                        rows.append({
                            "agent_server_id": agent_id,
                            "agent_healthy": agent_healthy,
                            "user_id": user_id,
                            "session_id": session_id,
                            "session_name": session_name,
                            "is_blocked": is_blocked,
                            "pane_id": pane.get("pane_id", ""),
                            "pane_status": pane.get("status", ""),
                            "pane_role": pane.get("role", ""),
                            "pane_title": pane.get("title", ""),
                        })
    return rows


def _extract_user_key(sess) -> str:
    """Extract a user identifier from session info."""
    if hasattr(sess, "user_info") and sess.user_info:
        ui = sess.user_info
        return ui.get("user_id") or ui.get("username") or ui.get("email") or "unknown"
    return "unknown"


def _extract_user_info(sess) -> dict:
    """Extract user_info dict from session info."""
    if hasattr(sess, "user_info"):
        return dict(sess.user_info) if sess.user_info else {}
    if hasattr(sess, "model_dump"):
        return sess.model_dump().get("user_info", {})
    return {}


def _session_to_dict(sess, ctrl: CentralController) -> dict:
    """Convert a session (PtySessionInfo or SessionInfo) to topology dict."""
    from aetherterm.common.models import PtySessionInfo

    panes = []
    if isinstance(sess, PtySessionInfo) and sess.windows:
        for win in sess.windows:
            for pane in win.panes:
                panes.append({
                    "pane_id": pane.pane_id,
                    "status": pane.status,
                    "role": pane.role,
                    "title": pane.title,
                    "cols": pane.cols,
                    "rows": pane.rows,
                    "window_id": win.window_id,
                    "window_name": win.name,
                })
    elif hasattr(sess, "pane_ids"):
        # Fallback: just pane_ids without details
        for pid in sess.pane_ids:
            panes.append({"pane_id": pid, "status": "unknown"})

    session_id = sess.session_id if hasattr(sess, "session_id") else ""
    is_blocked = False
    block_reason = None

    # Check blocking status from legacy tracking
    for block in ctrl.active_blocks.values():
        if session_id in block.affected_sessions:
            is_blocked = True
            block_reason = block.reason
            break

    return {
        "session_id": session_id,
        "name": getattr(sess, "name", ""),
        "is_blocked": is_blocked,
        "block_reason": block_reason,
        "pane_count": len(panes),
        "panes": panes,
        "created_at": getattr(sess, "created_at", None),
        "last_activity": getattr(sess, "last_activity", None),
    }


# ---------------------------------------------------------------------------
# Embedded Admin HTML (DataGrid)
# ---------------------------------------------------------------------------

_ADMIN_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ControlServer Admin</title>
<style>
  :root {
    --bg: #0f1117;
    --surface: #1a1d27;
    --border: #2d3148;
    --text: #e1e4ed;
    --text-dim: #8b8fa3;
    --accent: #6c7bf0;
    --success: #4ade80;
    --warning: #fbbf24;
    --danger: #f87171;
    --blocked: #ef4444;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
    background: var(--bg);
    color: var(--text);
    font-size: 13px;
    padding: 16px;
  }
  h1 { font-size: 18px; margin-bottom: 12px; color: var(--accent); }
  .toolbar {
    display: flex;
    gap: 12px;
    align-items: center;
    margin-bottom: 12px;
    flex-wrap: wrap;
  }
  .toolbar input {
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 6px 10px;
    border-radius: 4px;
    font-size: 13px;
    min-width: 220px;
  }
  .toolbar select {
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 6px 8px;
    border-radius: 4px;
    font-size: 13px;
  }
  .toolbar .stats {
    margin-left: auto;
    color: var(--text-dim);
    font-size: 12px;
  }
  .btn {
    padding: 6px 12px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--surface);
    color: var(--text);
    cursor: pointer;
    font-size: 12px;
  }
  .btn:hover { border-color: var(--accent); }
  .btn.danger { border-color: var(--danger); color: var(--danger); }
  .btn.danger:hover { background: var(--danger); color: #fff; }

  /* DataGrid */
  .datagrid {
    width: 100%;
    border-collapse: collapse;
    background: var(--surface);
    border-radius: 6px;
    overflow: hidden;
  }
  .datagrid th, .datagrid td {
    padding: 8px 12px;
    text-align: left;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
  }
  .datagrid th {
    background: #141722;
    color: var(--text-dim);
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    cursor: pointer;
    user-select: none;
    position: sticky;
    top: 0;
    z-index: 10;
  }
  .datagrid th:hover { color: var(--accent); }
  .datagrid th .sort-arrow { margin-left: 4px; opacity: 0.5; }
  .datagrid th.sorted .sort-arrow { opacity: 1; color: var(--accent); }
  .datagrid tr:hover td { background: rgba(108, 123, 240, 0.06); }
  .datagrid .group-row td {
    background: #161927;
    font-weight: 600;
    color: var(--accent);
    cursor: pointer;
  }
  .datagrid .group-row td:hover { text-decoration: underline; }

  /* Status badges */
  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
  }
  .badge.running { background: rgba(74, 222, 128, 0.15); color: var(--success); }
  .badge.blocked { background: rgba(239, 68, 68, 0.15); color: var(--blocked); }
  .badge.exited { background: rgba(139, 143, 163, 0.15); color: var(--text-dim); }
  .badge.healthy { background: rgba(74, 222, 128, 0.15); color: var(--success); }
  .badge.unhealthy { background: rgba(239, 68, 68, 0.15); color: var(--danger); }
  .badge.unknown { background: rgba(139, 143, 163, 0.15); color: var(--text-dim); }

  /* View toggle */
  .view-tabs { display: flex; gap: 2px; }
  .view-tabs .tab {
    padding: 6px 14px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--text-dim);
    cursor: pointer;
    font-size: 12px;
  }
  .view-tabs .tab:first-child { border-radius: 4px 0 0 4px; }
  .view-tabs .tab:last-child { border-radius: 0 4px 4px 0; }
  .view-tabs .tab.active {
    background: var(--accent);
    color: #fff;
    border-color: var(--accent);
  }

  .scroll-container {
    max-height: calc(100vh - 120px);
    overflow: auto;
    border-radius: 6px;
    border: 1px solid var(--border);
  }
  .no-data {
    text-align: center;
    padding: 40px;
    color: var(--text-dim);
  }
</style>
</head>
<body>

<h1>ControlServer Admin</h1>

<div class="toolbar">
  <div class="view-tabs">
    <button class="tab active" onclick="setView('tree')" id="tab-tree">Tree</button>
    <button class="tab" onclick="setView('flat')" id="tab-flat">Flat</button>
  </div>
  <input type="text" id="search" placeholder="Filter by agent, user, session, pane..."
         oninput="applyFilter()">
  <select id="status-filter" onchange="applyFilter()">
    <option value="">All Status</option>
    <option value="running">Running</option>
    <option value="blocked">Blocked</option>
    <option value="exited">Exited</option>
  </select>
  <button class="btn" onclick="refresh()">Refresh</button>
  <span class="stats" id="stats"></span>
</div>

<div class="scroll-container">
  <table class="datagrid" id="grid">
    <thead id="grid-head"></thead>
    <tbody id="grid-body"></tbody>
  </table>
  <div class="no-data" id="no-data" style="display:none">No data available</div>
</div>

<script>
const API_BASE = window.location.origin;
let currentView = 'tree';
let treeData = [];
let flatData = [];
let sortCol = '';
let sortAsc = true;
let expandedAgents = new Set();
let expandedUsers = new Set();

async function fetchData() {
  try {
    const [treeRes, flatRes] = await Promise.all([
      fetch(API_BASE + '/api/topology'),
      fetch(API_BASE + '/api/topology/flat'),
    ]);
    treeData = await treeRes.json();
    flatData = await flatRes.json();
    render();
  } catch (e) {
    document.getElementById('no-data').style.display = 'block';
    document.getElementById('no-data').textContent = 'Failed to load: ' + e.message;
  }
}

function setView(v) {
  currentView = v;
  document.getElementById('tab-tree').classList.toggle('active', v === 'tree');
  document.getElementById('tab-flat').classList.toggle('active', v === 'flat');
  render();
}

function refresh() { fetchData(); }

function applyFilter() { render(); }

function getFilter() {
  const q = document.getElementById('search').value.toLowerCase();
  const st = document.getElementById('status-filter').value;
  return { q, st };
}

function statusBadge(status) {
  if (!status) return '';
  const cls = status === 'running' ? 'running'
    : status === 'blocked' ? 'blocked'
    : status === 'exited' ? 'exited' : 'unknown';
  return '<span class="badge ' + cls + '">' + status + '</span>';
}

function healthBadge(h) {
  if (h === null || h === undefined) return '<span class="badge unknown">-</span>';
  return h ? '<span class="badge healthy">healthy</span>'
           : '<span class="badge unhealthy">unhealthy</span>';
}

// ---------- TREE VIEW ----------

function renderTree() {
  const { q, st } = getFilter();
  const head = document.getElementById('grid-head');
  const body = document.getElementById('grid-body');

  head.innerHTML = '<tr>'
    + '<th style="width:30px"></th>'
    + '<th>Agent Server</th>'
    + '<th>Health</th>'
    + '<th>User</th>'
    + '<th>Session</th>'
    + '<th>Pane</th>'
    + '<th>Status</th>'
    + '<th>Role</th>'
    + '<th>Window</th>'
    + '</tr>';

  let html = '';
  let totalPanes = 0;
  let totalSessions = 0;

  for (const agent of treeData) {
    const aid = agent.agent_server_id;
    const aMatch = !q || aid.toLowerCase().includes(q);
    const expanded = expandedAgents.has(aid);

    // Agent row
    html += '<tr class="group-row" onclick="toggleAgent(\\'' + aid + '\\')">'
      + '<td>' + (expanded ? '&#x25BC;' : '&#x25B6;') + '</td>'
      + '<td colspan="2">' + aid + ' ' + healthBadge(agent.health && agent.health.is_healthy) + '</td>'
      + '<td>' + agent.user_count + ' users</td>'
      + '<td>' + agent.session_count + ' sessions</td>'
      + '<td>' + agent.pane_count + ' panes</td>'
      + '<td></td><td></td><td></td></tr>';

    if (!expanded) continue;

    for (const user of agent.users) {
      const uid = user.user_id;
      const uKey = aid + ':' + uid;
      const uExpanded = expandedUsers.has(uKey);
      const uMatch = aMatch || uid.toLowerCase().includes(q);

      html += '<tr class="group-row" onclick="toggleUser(\\'' + uKey + '\\')">'
        + '<td></td>'
        + '<td>' + (uExpanded ? '&#x25BC;' : '&#x25B6;') + '</td>'
        + '<td></td>'
        + '<td>' + uid + '</td>'
        + '<td>' + user.session_count + ' sessions</td>'
        + '<td>' + user.pane_count + ' panes</td>'
        + '<td></td><td></td><td></td></tr>';

      if (!uExpanded) continue;

      for (const sess of user.sessions) {
        const sMatch = uMatch
          || sess.session_id.toLowerCase().includes(q)
          || (sess.name || '').toLowerCase().includes(q);

        totalSessions++;

        for (const pane of (sess.panes || [])) {
          if (st && pane.status !== st) continue;
          if (q && !sMatch && !pane.pane_id.toLowerCase().includes(q)
              && !(pane.role || '').toLowerCase().includes(q)) continue;

          totalPanes++;
          html += '<tr>'
            + '<td></td><td></td><td></td><td></td>'
            + '<td>' + sess.session_id.substring(0, 16)
              + (sess.name ? ' (' + sess.name + ')' : '')
              + (sess.is_blocked ? ' ' + statusBadge('blocked') : '') + '</td>'
            + '<td style="font-family:monospace;font-size:12px">' + pane.pane_id + '</td>'
            + '<td>' + statusBadge(pane.status) + '</td>'
            + '<td>' + (pane.role || '-') + '</td>'
            + '<td>' + (pane.window_name || pane.window_id || '-') + '</td>'
            + '</tr>';
        }

        if (!sess.panes || sess.panes.length === 0) {
          totalPanes++;
          html += '<tr>'
            + '<td></td><td></td><td></td><td></td>'
            + '<td>' + sess.session_id.substring(0, 16) + '</td>'
            + '<td colspan="4" style="color:var(--text-dim)">No panes</td></tr>';
        }
      }
    }
  }

  body.innerHTML = html;
  document.getElementById('stats').textContent =
    treeData.length + ' agents, ' + totalSessions + ' sessions, ' + totalPanes + ' panes';
  document.getElementById('no-data').style.display = treeData.length ? 'none' : 'block';
}

function toggleAgent(aid) {
  if (expandedAgents.has(aid)) expandedAgents.delete(aid);
  else expandedAgents.add(aid);
  render();
}

function toggleUser(key) {
  if (expandedUsers.has(key)) expandedUsers.delete(key);
  else expandedUsers.add(key);
  render();
}

// ---------- FLAT VIEW ----------

const FLAT_COLS = [
  { key: 'agent_server_id', label: 'Agent Server' },
  { key: 'agent_healthy', label: 'Health' },
  { key: 'user_id', label: 'User' },
  { key: 'session_id', label: 'Session' },
  { key: 'session_name', label: 'Session Name' },
  { key: 'is_blocked', label: 'Blocked' },
  { key: 'pane_id', label: 'Pane' },
  { key: 'pane_status', label: 'Status' },
  { key: 'pane_role', label: 'Role' },
];

function renderFlat() {
  const { q, st } = getFilter();
  const head = document.getElementById('grid-head');
  const body = document.getElementById('grid-body');

  head.innerHTML = '<tr>' + FLAT_COLS.map(c => {
    const sorted = sortCol === c.key;
    const arrow = sorted ? (sortAsc ? '&#x25B2;' : '&#x25BC;') : '&#x25B4;';
    return '<th class="' + (sorted ? 'sorted' : '') + '" onclick="sortBy(\\'' + c.key + '\\')">'
      + c.label + ' <span class="sort-arrow">' + arrow + '</span></th>';
  }).join('') + '</tr>';

  let filtered = flatData.filter(row => {
    if (st && row.pane_status !== st) return false;
    if (q) {
      const text = Object.values(row).join(' ').toLowerCase();
      if (!text.includes(q)) return false;
    }
    return true;
  });

  if (sortCol) {
    filtered.sort((a, b) => {
      let va = a[sortCol] ?? '';
      let vb = b[sortCol] ?? '';
      if (typeof va === 'string') va = va.toLowerCase();
      if (typeof vb === 'string') vb = vb.toLowerCase();
      if (va < vb) return sortAsc ? -1 : 1;
      if (va > vb) return sortAsc ? 1 : -1;
      return 0;
    });
  }

  let html = '';
  for (const row of filtered) {
    html += '<tr>';
    for (const c of FLAT_COLS) {
      const val = row[c.key];
      if (c.key === 'agent_healthy') {
        html += '<td>' + healthBadge(val) + '</td>';
      } else if (c.key === 'pane_status') {
        html += '<td>' + statusBadge(val) + '</td>';
      } else if (c.key === 'is_blocked') {
        html += '<td>' + (val ? statusBadge('blocked') : '-') + '</td>';
      } else if (c.key === 'pane_id' || c.key === 'session_id') {
        html += '<td style="font-family:monospace;font-size:12px">'
          + ((val || '').substring(0, 20) || '-') + '</td>';
      } else {
        html += '<td>' + (val || '-') + '</td>';
      }
    }
    html += '</tr>';
  }

  body.innerHTML = html;
  document.getElementById('stats').textContent =
    filtered.length + ' of ' + flatData.length + ' rows';
  document.getElementById('no-data').style.display = filtered.length ? 'none' : 'block';
}

function sortBy(col) {
  if (sortCol === col) sortAsc = !sortAsc;
  else { sortCol = col; sortAsc = true; }
  render();
}

function render() {
  if (currentView === 'tree') renderTree();
  else renderFlat();
}

// Initial load + auto-refresh
fetchData();
setInterval(fetchData, 10000);
</script>
</body>
</html>
"""

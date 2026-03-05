"""ChildLauncher — Abstraction Layer for Child Agent Lifecycle

PoC: tmux pane または subprocess で子Agentを起動
将来: AetherTerm pane API (session_registry.split_pane()) に移行

Usage:
    launcher = TmuxPaneLauncher()  # tmux内
    launcher = SubprocessLauncher()  # tmuxなし
    child_id = await launcher.launch("coder", "coder", "tcp://localhost:5570")
    await launcher.terminate("coder")
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
from abc import ABC, abstractmethod
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ChildLauncher(ABC):
    """子Agent起動の抽象クラス

    tmux pane (PoC) → AetherTerm pane (将来) への移行を
    この抽象化層で吸収する。
    """

    @abstractmethod
    async def launch(
        self,
        agent_id: str,
        role: str,
        router_addr: str,
        command: Optional[str] = None,
    ) -> str:
        """子プロセスを起動

        Args:
            agent_id: Agent identifier
            role: Agent role (coder, reviewer, tester, etc.)
            router_addr: ZMQ ROUTER address to connect to
            command: Override command (default: child_agent.py module)

        Returns:
            child_id (agent_id or pane_id)
        """

    @abstractmethod
    async def terminate(self, child_id: str) -> None:
        """子プロセスを終了"""

    @abstractmethod
    async def is_alive(self, child_id: str) -> bool:
        """子プロセスが生存しているか確認"""


class TmuxPaneLauncher(ChildLauncher):
    """PoC: tmuxコマンドで子paneを作成して子Agentを起動

    tmux split-window で新しいpaneを作り、その中でchild_agent.pyを実行。
    use_claude=True の場合は agent_shell_child.py を起動する。
    """

    def __init__(
        self,
        session_name: Optional[str] = None,
        use_claude: bool = False,
        workspace: Optional[str] = None,
        claude_model: Optional[str] = None,
    ):
        self._session_name = session_name  # None = current session
        self._pane_ids: Dict[str, str] = {}  # agent_id → tmux pane_id
        self._use_claude = use_claude
        self._workspace = workspace
        self._claude_model = claude_model

    async def launch(
        self,
        agent_id: str,
        role: str,
        router_addr: str,
        command: Optional[str] = None,
    ) -> str:
        if not shutil.which("tmux"):
            raise RuntimeError("tmux not found in PATH")

        if command:
            cmd = command
        elif self._use_claude:
            module = "experimental.zmq_agent_poc.agent_shell_child"
            cmd = (
                f"{sys.executable} -m {module} "
                f"--agent-id {agent_id} --role {role} --router {router_addr}"
            )
            if self._workspace:
                cmd += f" --workspace {self._workspace}"
            if self._claude_model:
                cmd += f" --model {self._claude_model}"
        else:
            cmd = (
                f"{sys.executable} -m experimental.zmq_agent_poc.child_agent "
                f"--agent-id {agent_id} --role {role} --router {router_addr}"
            )

        # Build tmux command
        tmux_args = ["tmux", "split-window", "-h", "-d"]
        if self._session_name:
            tmux_args.extend(["-t", self._session_name])
        # Set pane title and environment variables
        tmux_args.extend([
            "-e", f"AGENT_ID={agent_id}",
            "-e", f"AGENT_ROLE={role}",
            "-e", f"AGENT_ROUTER={router_addr}",
            "-P", "-F", "#{pane_id}",  # Print pane ID
            cmd,
        ])

        proc = await asyncio.create_subprocess_exec(
            *tmux_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=_project_root(),
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err = stderr.decode().strip()
            raise RuntimeError(f"tmux split-window failed: {err}")

        pane_id = stdout.decode().strip()
        self._pane_ids[agent_id] = pane_id
        logger.info(f"Launched {agent_id} in tmux pane {pane_id}")
        return agent_id

    async def terminate(self, child_id: str) -> None:
        pane_id = self._pane_ids.pop(child_id, None)
        if not pane_id:
            logger.warning(f"No tmux pane for {child_id}")
            return

        proc = await asyncio.create_subprocess_exec(
            "tmux", "kill-pane", "-t", pane_id,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        logger.info(f"Terminated tmux pane {pane_id} ({child_id})")

    async def is_alive(self, child_id: str) -> bool:
        pane_id = self._pane_ids.get(child_id)
        if not pane_id:
            return False

        proc = await asyncio.create_subprocess_exec(
            "tmux", "has-session", "-t", pane_id,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        return proc.returncode == 0


class SubprocessLauncher(ChildLauncher):
    """フォールバック: asyncio.create_subprocess_exec (tmuxなし環境用)

    各子Agentをサブプロセスとして起動。
    use_claude=True の場合は agent_shell_child.py を起動する。
    """

    def __init__(
        self,
        use_claude: bool = False,
        workspace: Optional[str] = None,
        claude_model: Optional[str] = None,
    ):
        self._processes: Dict[str, asyncio.subprocess.Process] = {}
        self._use_claude = use_claude
        self._workspace = workspace
        self._claude_model = claude_model

    async def launch(
        self,
        agent_id: str,
        role: str,
        router_addr: str,
        command: Optional[str] = None,
    ) -> str:
        env = {
            **os.environ,
            "AGENT_ID": agent_id,
            "AGENT_ROLE": role,
            "AGENT_ROUTER": router_addr,
        }
        if self._workspace:
            env["AGENT_WORKSPACE"] = self._workspace

        if command:
            # Custom command: run via shell
            proc = await asyncio.create_subprocess_shell(
                command, env=env, cwd=_project_root(),
            )
        else:
            module = (
                "experimental.zmq_agent_poc.agent_shell_child"
                if self._use_claude
                else "experimental.zmq_agent_poc.child_agent"
            )
            args = [
                sys.executable, "-m", module,
                "--agent-id", agent_id,
                "--role", role,
                "--router", router_addr,
            ]
            if self._use_claude and self._workspace:
                args.extend(["--workspace", self._workspace])
            if self._use_claude and self._claude_model:
                args.extend(["--model", self._claude_model])

            proc = await asyncio.create_subprocess_exec(
                *args, env=env, cwd=_project_root(),
            )

        self._processes[agent_id] = proc
        logger.info(f"Launched {agent_id} as subprocess (pid={proc.pid})")
        return agent_id

    async def terminate(self, child_id: str) -> None:
        proc = self._processes.pop(child_id, None)
        if not proc:
            logger.warning(f"No subprocess for {child_id}")
            return

        try:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
            logger.info(f"Terminated subprocess {child_id} (pid={proc.pid})")
        except ProcessLookupError:
            pass

    async def is_alive(self, child_id: str) -> bool:
        proc = self._processes.get(child_id)
        if not proc:
            return False
        return proc.returncode is None


class AetherTermPaneLauncher(ChildLauncher):
    """AetherTerm pane API経由でペーンを作成し、子Agentを起動

    AgentServerの /ws/agent/{agent_id} WebSocket経由で split_pane コマンドを送信。
    session_registry._fork_pane() でPTYが作成され、ブラウザのフロントエンドに
    新しいペーンが表示される。

    前提: AgentServerが起動済み (make run-agentserver)

    Usage:
        launcher = AetherTermPaneLauncher(server_url="ws://localhost:57575")
        await launcher.connect()
        await launcher.launch("coder", "coder", "tcp://localhost:5570")
    """

    def __init__(
        self,
        server_url: str = "ws://localhost:57575",
        session_id: str = "",
        use_claude: bool = True,
        workspace: Optional[str] = None,
        claude_model: Optional[str] = None,
    ):
        self._server_url = server_url
        self._session_id = session_id
        self._use_claude = use_claude
        self._workspace = workspace
        self._claude_model = claude_model
        self._pane_ids: Dict[str, str] = {}  # agent_id → pane_id
        self._messenger = None
        self._connected = False

    async def connect(self) -> None:
        """AgentServerにWebSocket接続し、セッションを特定する"""
        from aetherterm.common.agent_messenger import InterAgentMessenger

        self._messenger = InterAgentMessenger(
            agent_id="orchestrator",
            server_url=self._server_url,
        )
        if not await self._messenger.connect():
            raise RuntimeError(
                f"Cannot connect to AgentServer at {self._server_url}. "
                "Is AgentServer running? (make run-agentserver)"
            )
        self._connected = True

        # Auto-detect session if not specified
        if not self._session_id:
            self._session_id = await self._detect_session()

        logger.info(
            f"AetherTermPaneLauncher connected: server={self._server_url}, "
            f"session={self._session_id}"
        )

    async def disconnect(self) -> None:
        """WebSocket切断"""
        if self._messenger:
            await self._messenger.disconnect()
        self._connected = False

    async def _detect_session(self) -> str:
        """REST APIでアクティブなセッションを取得"""
        import httpx

        http_url = self._server_url.replace("ws://", "http://").replace(
            "wss://", "https://"
        )
        async with httpx.AsyncClient(base_url=http_url, timeout=5.0) as client:
            resp = await client.get("/api/tmux/sessions")
            resp.raise_for_status()
            sessions = resp.json()

        if not sessions:
            raise RuntimeError(
                "No active AetherTerm sessions. "
                "Open AetherTerm in a browser first."
            )

        session_id = sessions[0]["session_id"]
        logger.info(f"Auto-detected session: {session_id}")
        return session_id

    async def launch(
        self,
        agent_id: str,
        role: str,
        router_addr: str,
        command: Optional[str] = None,
    ) -> str:
        if not self._connected or not self._messenger:
            raise RuntimeError("Not connected. Call connect() first.")

        # Build command for the pane
        if command:
            cmd_list = ["bash", "-c", f"unset CLAUDECODE; exec {command}"]
        elif self._use_claude:
            module = "experimental.zmq_agent_poc.agent_shell_child"
            inner = (
                f"{sys.executable} -m {module} "
                f"--agent-id {agent_id} --role {role} --router {router_addr}"
            )
            if self._workspace:
                inner += f" --workspace {self._workspace}"
            if self._claude_model:
                inner += f" --model {self._claude_model}"
            # Wrap to unset CLAUDECODE for nested claude execution
            cmd_list = ["bash", "-c", f"unset CLAUDECODE; exec {inner}"]
        else:
            module = "experimental.zmq_agent_poc.child_agent"
            cmd_list = [
                sys.executable, "-m", module,
                "--agent-id", agent_id, "--role", role, "--router", router_addr,
            ]

        env = {
            "AGENT_ID": agent_id,
            "AGENT_ROLE": role,
            "AGENT_ROUTER": router_addr,
        }
        if self._workspace:
            env["AGENT_WORKSPACE"] = self._workspace

        # Call split_pane via WebSocket → creates actual PTY pane
        result = await self._messenger.split_pane(
            session_id=self._session_id,
            direction="h",
            cmd=cmd_list,
            env=env,
            role=role,
            timeout=10.0,
        )

        if not result.get("success"):
            error = result.get("error", "unknown error")
            raise RuntimeError(f"split_pane failed: {error}")

        pane_data = result.get("data", {})
        pane_id = pane_data.get("pane_id", agent_id)
        self._pane_ids[agent_id] = pane_id

        logger.info(
            f"Created AetherTerm pane: agent={agent_id}, role={role}, pane={pane_id}"
        )
        return agent_id

    async def terminate(self, child_id: str) -> None:
        """ペーンを閉じる（send_keys で exit を送信）"""
        pane_id = self._pane_ids.pop(child_id, None)
        if not pane_id or not self._messenger:
            return

        # Send Ctrl+C then exit
        try:
            await self._messenger.send_keys(pane_id, "\x03")
            await asyncio.sleep(0.3)
            await self._messenger.send_keys(pane_id, "exit\n")
        except Exception as e:
            logger.warning(f"Failed to terminate pane {pane_id}: {e}")

        logger.info(f"Terminated AetherTerm pane {pane_id} ({child_id})")

    async def is_alive(self, child_id: str) -> bool:
        pane_id = self._pane_ids.get(child_id)
        if not pane_id or not self._messenger:
            return False

        try:
            panes = await self._messenger.list_panes(self._session_id)
            return any(p.get("pane_id") == pane_id for p in panes)
        except Exception:
            return False


def _project_root() -> str:
    """プロジェクトルートを返す"""
    # experimental/zmq_agent_poc/ → app/terminal/
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(here))

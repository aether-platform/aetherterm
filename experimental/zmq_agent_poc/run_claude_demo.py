"""Demo: Claude-powered Code Review Workflow

AgentShellChild を使い、実際の claude CLI で
fibonacci関数の実装→レビュー→テスト作成を行うデモ。

Scenario:
  1. Shared workspace作成
  2. coder:    claude -p → fibonacci関数を実装
  3. reviewer: claude -p → コードレビュー + coderにDM
  4. tester:   claude -p → テスト作成
  5. broadcast → shutdown

Usage:
    cd /mnt/c/workspace/vibecoding-platform/app/terminal

    # 実際のclaude CLIでデモ実行
    python -m experimental.zmq_agent_poc.run_claude_demo

    # Stubモード（claude未使用、動作確認用）
    python -m experimental.zmq_agent_poc.run_claude_demo --dry-run

    # カスタムworkspace
    python -m experimental.zmq_agent_poc.run_claude_demo --workspace /tmp/my_workspace

    # Subprocess mode（各agentを別プロセスで起動）
    python -m experimental.zmq_agent_poc.run_claude_demo --launcher subprocess
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shutil
import tempfile
import time
from typing import Dict, Optional

from aetherterm.common.agent_protocol import AgentMessage, MessageType

from .agent_shell_child import AgentShellChild
from .child_launcher import (
    AetherTermPaneLauncher,
    ChildLauncher,
    SubprocessLauncher,
    TmuxPaneLauncher,
)
from .parent_agent import ParentAgent

logger = logging.getLogger(__name__)

# ANSI colors
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_BLUE = "\033[34m"
C_MAGENTA = "\033[35m"
C_CYAN = "\033[36m"
C_RED = "\033[31m"


def log_step(step: int, total: int, msg: str) -> None:
    print(f"\n{C_BOLD}{C_CYAN}[{step}/{total}]{C_RESET} {msg}")


def log_result(agent: str, content: str) -> None:
    print(f"  {C_GREEN}✓{C_RESET} [{C_YELLOW}{agent}{C_RESET}] {content}")


def log_info(msg: str) -> None:
    print(f"  {C_DIM}→ {msg}{C_RESET}")


class InProcessClaudeLauncher(ChildLauncher):
    """全AgentShellChildを同一プロセス内で起動

    AgentShellChild（claude実行可能）をasyncio.create_taskで直接起動。
    tmux pane不要、デバッグ・テストに最適。
    """

    def __init__(
        self,
        workspace: Optional[str] = None,
        claude_model: Optional[str] = None,
        use_claude: bool = True,
        timeout: float = 120.0,
    ):
        self._workspace = workspace
        self._claude_model = claude_model
        self._use_claude = use_claude
        self._timeout = timeout
        self._children: Dict[str, AgentShellChild] = {}
        self._tasks: Dict[str, asyncio.Task] = {}

    async def launch(
        self, agent_id: str, role: str, router_addr: str, command=None
    ) -> str:
        child = AgentShellChild(
            agent_id=agent_id,
            role=role,
            router_addr=router_addr,
            workspace=self._workspace,
            claude_model=self._claude_model,
            use_claude=self._use_claude,
            timeout=self._timeout,
        )
        self._children[agent_id] = child
        _register_default_handlers(child)

        task = asyncio.create_task(self._run_child(child))
        self._tasks[agent_id] = task
        return agent_id

    async def _run_child(self, child: AgentShellChild) -> None:
        await child.start()
        try:
            while child.is_running:
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        finally:
            if child.is_running:
                await child.stop()

    async def terminate(self, child_id: str) -> None:
        child = self._children.pop(child_id, None)
        task = self._tasks.pop(child_id, None)
        if child and child.is_running:
            await child.stop()
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def is_alive(self, child_id: str) -> bool:
        child = self._children.get(child_id)
        return child is not None and child.is_running


def _register_default_handlers(child: AgentShellChild) -> None:
    """AgentShellChildにデフォルトハンドラを登録"""

    @child.on_message(MessageType.TASK_CREATE)
    async def handle_task(msg: AgentMessage):
        task_id = msg.payload.get("task_id")
        description = msg.payload.get("description", "")
        context = msg.payload.get("context", {})

        # Build prompt
        prompt = description
        if context.get("code"):
            prompt += f"\n\nCode:\n```python\n{context['code']}\n```"
        if context.get("files"):
            prompt += f"\n\nFiles in workspace: {', '.join(context['files'])}"

        logger.info(f"[{child.agent_id}] Processing: {description[:60]}")
        result_text = await child.think(prompt)

        # reviewer → coder DM
        if child.role == "reviewer" and context.get("code"):
            await child.send_dm("coder", f"Review feedback:\n{result_text}")

        await child.complete_task(task_id, {"output": result_text})

    @child.on_message(MessageType.AGENT_DM)
    async def handle_dm(msg: AgentMessage):
        content = msg.payload.get("content", "")
        logger.info(f"[{child.agent_id}] DM from {msg.from_agent}: {content[:80]}")

    @child.on_message(MessageType.AGENT_BROADCAST)
    async def handle_broadcast(msg: AgentMessage):
        content = msg.payload.get("content", "")
        logger.info(f"[{child.agent_id}] Broadcast: {content[:80]}")


async def run_claude_demo(
    launcher_type: str = "inprocess",
    port: int = 5572,
    workspace: Optional[str] = None,
    claude_model: Optional[str] = None,
    use_claude: bool = True,
    timeout: float = 120.0,
):
    """Claude-powered code review workflow"""
    total_steps = 9

    print(f"\n{C_BOLD}{C_MAGENTA}{'=' * 64}")
    print(f"  ZMQ Agent-to-Agent Communication")
    print(f"  Claude-Powered Code Review Workflow")
    mode_label = "LIVE (claude CLI)" if use_claude else "DRY RUN (stubs)"
    print(f"  Mode: {mode_label}")
    print(f"{'=' * 64}{C_RESET}\n")

    # --- Setup workspace ---
    cleanup_workspace = False
    if not workspace:
        workspace = tempfile.mkdtemp(prefix="zmq_agent_poc_")
        cleanup_workspace = True
    os.makedirs(workspace, exist_ok=True)
    log_info(f"Workspace: {workspace}")

    # --- Launcher selection ---
    launcher: ChildLauncher
    aetherterm_launcher: Optional[AetherTermPaneLauncher] = None

    if launcher_type == "inprocess":
        launcher = InProcessClaudeLauncher(
            workspace=workspace,
            claude_model=claude_model,
            use_claude=use_claude,
            timeout=timeout,
        )
        log_info("Launcher: InProcessClaudeLauncher (no pane creation)")
    elif launcher_type == "subprocess":
        launcher = SubprocessLauncher(
            use_claude=use_claude,
            workspace=workspace,
            claude_model=claude_model,
        )
        log_info("Launcher: SubprocessLauncher (background processes)")
    elif launcher_type == "tmux":
        launcher = TmuxPaneLauncher(
            use_claude=use_claude,
            workspace=workspace,
            claude_model=claude_model,
        )
        log_info("Launcher: TmuxPaneLauncher (tmux split-window)")
    elif launcher_type == "aetherterm":
        server_url = os.environ.get("AGENTSERVER_URL", "ws://localhost:57575")
        aetherterm_launcher = AetherTermPaneLauncher(
            server_url=server_url,
            use_claude=use_claude,
            workspace=workspace,
            claude_model=claude_model,
        )
        log_info(f"Launcher: AetherTermPaneLauncher ({server_url})")
        log_info("Connecting to AgentServer...")
        await aetherterm_launcher.connect()
        launcher = aetherterm_launcher
        log_info(f"Connected! Session: {aetherterm_launcher._session_id}")
    else:
        raise ValueError(f"Unknown launcher: {launcher_type}")

    # --- Step 1: Start parent ---
    log_step(1, total_steps, "Starting ParentAgent (ZMQ ROUTER)")
    parent = ParentAgent(router_port=port, launcher=launcher)

    registered = []

    def on_registered(agent_id, role):
        registered.append(agent_id)
        log_result(agent_id, f"Registered (role={role})")

    parent.set_on_agent_registered(on_registered)
    await parent.start()
    log_info(f"ROUTER on tcp://*:{port}")

    demo_start = time.time()

    try:
        # --- Step 2: Spawn agents ---
        log_step(2, total_steps, "Spawning AgentShell agents: coder, reviewer, tester")
        agents = [("coder", "coder"), ("reviewer", "reviewer"), ("tester", "tester")]

        for agent_id, role in agents:
            await parent.spawn_child(agent_id, role)
            log_info(f"Spawned {agent_id} (AgentShellChild)")

        # Wait for registration
        log_info("Waiting for agent registration...")
        for agent_id, _ in agents:
            if not await parent.wait_for_agent(agent_id, timeout=15.0):
                print(f"  {C_RED}✗ Failed: {agent_id}{C_RESET}")
                return
        print(f"\n  {C_GREEN}All {len(agents)} agents registered!{C_RESET}")

        # --- Step 3: coder → implement ---
        log_step(
            3,
            total_steps,
            "Task → coder: Implement fibonacci function",
        )
        coder_prompt = (
            "Write a Python function `fibonacci(n: int) -> int` that returns "
            "the nth Fibonacci number. Use an iterative approach for O(n) time "
            "and O(1) space. Include a docstring and handle edge cases (n < 0). "
            "Output ONLY the Python code."
        )
        coder_future = await parent.send_task(
            "coder",
            task_type="implement",
            description=coder_prompt,
            context={"language": "python", "workspace": workspace},
        )

        # --- Step 4: Wait for coder ---
        log_step(4, total_steps, "Waiting for coder...")
        coder_result = await asyncio.wait_for(coder_future, timeout=timeout + 10)
        code = coder_result["result"].get("output", "")
        log_result("coder", f"Code generated ({len(code)} chars)")
        _print_code_preview(code, max_lines=8)

        # --- Step 5: reviewer → review ---
        log_step(
            5,
            total_steps,
            "Task → reviewer: Review the fibonacci implementation",
        )
        reviewer_prompt = (
            "Review the following Python code for correctness, edge cases, "
            "performance, and code quality. Provide a structured review."
        )
        reviewer_future = await parent.send_task(
            "reviewer",
            task_type="review",
            description=reviewer_prompt,
            context={"code": code},
        )

        # --- Step 6: Wait for reviewer ---
        log_step(6, total_steps, "Waiting for reviewer...")
        reviewer_result = await asyncio.wait_for(reviewer_future, timeout=timeout + 10)
        review = reviewer_result["result"].get("output", "")
        log_result("reviewer", "Review completed")
        _print_code_preview(review, max_lines=10)

        # Wait for DM delivery
        await asyncio.sleep(1.0)

        # --- Step 7: tester → write tests ---
        log_step(
            7,
            total_steps,
            "Task → tester: Write tests for fibonacci",
        )
        tester_prompt = (
            "Write comprehensive pytest test cases for the fibonacci function. "
            "Include: base cases (0, 1), normal cases, edge cases (negative input), "
            "and a few larger values. Output ONLY the Python test code."
        )
        tester_future = await parent.send_task(
            "tester",
            task_type="test",
            description=tester_prompt,
            context={"code": code},
        )

        # --- Step 8: Wait for tester ---
        log_step(8, total_steps, "Waiting for tester...")
        tester_result = await asyncio.wait_for(tester_future, timeout=timeout + 10)
        tests = tester_result["result"].get("output", "")
        log_result("tester", f"Tests generated ({len(tests)} chars)")
        _print_code_preview(tests, max_lines=8)

        # --- Step 9: Broadcast + shutdown ---
        log_step(9, total_steps, "Broadcasting completion + shutdown")
        await parent.broadcast(
            "Workflow complete! All tasks finished successfully."
        )
        await asyncio.sleep(1.0)

        elapsed = time.time() - demo_start
        print(f"\n{C_BOLD}{C_GREEN}{'=' * 64}")
        print(f"  Demo Complete! ({elapsed:.1f}s total)")
        print(f"{'─' * 64}")
        print(f"  Agents: 3 (coder, reviewer, tester)")
        print(f"  Claude: {'YES' if use_claude else 'NO (stubs)'}")
        print(f"  Workspace: {workspace}")
        print(f"  Flow: implement → review (+ DM) → test → broadcast")
        print(f"{'=' * 64}{C_RESET}\n")

    except asyncio.TimeoutError:
        print(f"\n  {C_RED}{C_BOLD}✗ Timeout{C_RESET}")
    except Exception as e:
        print(f"\n  {C_RED}{C_BOLD}✗ Error: {e}{C_RESET}")
        logger.exception("Demo error")
    finally:
        await parent.stop()
        log_info("ParentAgent stopped")

        if aetherterm_launcher:
            await aetherterm_launcher.disconnect()
            log_info("Disconnected from AgentServer")

        if cleanup_workspace:
            log_info(f"Workspace preserved at: {workspace}")
            log_info("(Delete manually when no longer needed)")


def _print_code_preview(text: str, max_lines: int = 8) -> None:
    """コード出力のプレビュー表示"""
    lines = text.strip().split("\n")
    print(f"{C_DIM}")
    for line in lines[:max_lines]:
        print(f"    {line}")
    if len(lines) > max_lines:
        print(f"    ... ({len(lines) - max_lines} more lines)")
    print(f"{C_RESET}")


def _in_tmux() -> bool:
    return bool(os.environ.get("TMUX"))


def main():
    parser = argparse.ArgumentParser(
        description="ZMQ Agent PoC - Claude-Powered Code Review Workflow",
    )
    parser.add_argument(
        "--launcher",
        choices=["inprocess", "subprocess", "tmux", "aetherterm"],
        default="inprocess",
        help="Launcher type (default: inprocess). "
        "aetherterm: creates panes in AgentServer (requires running AgentServer)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5572,
        help="ZMQ ROUTER port (default: 5572)",
    )
    parser.add_argument(
        "--workspace",
        default=None,
        help="Shared workspace directory",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Claude model (e.g. claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use stubs instead of claude (no API calls)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Per-task timeout in seconds (default: 120)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    if not args.verbose:
        logging.getLogger("aetherterm").setLevel(logging.WARNING)

    asyncio.run(
        run_claude_demo(
            launcher_type=args.launcher,
            port=args.port,
            workspace=args.workspace,
            claude_model=args.model,
            use_claude=not args.dry_run,
            timeout=args.timeout,
        )
    )


if __name__ == "__main__":
    main()

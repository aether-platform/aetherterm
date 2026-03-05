"""Demo: コードレビューワークフロー

3つのAgent (coder, reviewer, tester) を起動し、
fibonacci関数の実装→レビュー→テスト作成のワークフローを実行。

Scenario:
  1. Parent spawns 3 agents: coder, reviewer, tester
  2. Parent → coder: TASK_CREATE "Implement fibonacci function"
  3. coder → TASK_COMPLETE with code
  4. Parent → reviewer: TASK_CREATE "Review this code"
  5. reviewer → sends DM to coder with feedback
  6. coder → receives DM, acknowledges
  7. Parent → tester: TASK_CREATE "Write tests for fibonacci"
  8. tester → TASK_COMPLETE
  9. Parent → broadcast "Workflow complete" → shutdown all

Usage:
    # tmux内で実行
    cd /mnt/c/workspace/vibecoding-platform/app/terminal
    python -m experimental.zmq_agent_poc.run_demo

    # tmuxなし (subprocess mode)
    python -m experimental.zmq_agent_poc.run_demo --launcher subprocess

    # In-process mode (全てシングルプロセスで動作、デバッグ用)
    python -m experimental.zmq_agent_poc.run_demo --launcher inprocess
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shutil
import sys
import time

from aetherterm.common.agent_protocol import AgentMessage, MessageType

from .child_agent import ChildAgent
from .child_launcher import (
    AetherTermPaneLauncher,
    ChildLauncher,
    SubprocessLauncher,
    TmuxPaneLauncher,
)
from .parent_agent import ParentAgent

logger = logging.getLogger(__name__)

# ANSI colors for console output
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_BLUE = "\033[34m"
C_MAGENTA = "\033[35m"
C_CYAN = "\033[36m"
C_DIM = "\033[2m"


def log_step(step: int, total: int, msg: str) -> None:
    print(f"\n{C_BOLD}{C_CYAN}[{step}/{total}]{C_RESET} {msg}")


def log_result(agent: str, content: str) -> None:
    print(f"  {C_GREEN}✓{C_RESET} [{C_YELLOW}{agent}{C_RESET}] {content}")


def log_info(msg: str) -> None:
    print(f"  {C_DIM}→ {msg}{C_RESET}")


class InProcessLauncher(ChildLauncher):
    """全子Agentを同一プロセス内で起動（デバッグ用）

    subprocessやtmuxを使わず、asyncio.create_taskで直接起動。
    """

    def __init__(self):
        self._children: dict[str, ChildAgent] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    async def launch(
        self, agent_id: str, role: str, router_addr: str, command=None
    ) -> str:
        child = ChildAgent(agent_id, role, router_addr)
        self._children[agent_id] = child

        # Register default handlers
        _register_default_handlers(child)

        # Start in background
        task = asyncio.create_task(self._run_child(child))
        self._tasks[agent_id] = task
        return agent_id

    async def _run_child(self, child: ChildAgent) -> None:
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


def _register_default_handlers(child: ChildAgent) -> None:
    """子Agentにデフォルトハンドラを登録"""

    @child.on_message(MessageType.TASK_CREATE)
    async def handle_task(msg: AgentMessage):
        task_id = msg.payload.get("task_id")
        description = msg.payload.get("description", "")
        context = msg.payload.get("context", {})

        logger.info(f"[{child.agent_id}] Processing task: {description}")

        # AI stub で応答生成
        result_text = await child.think(description)

        # reviewer はコーダーにDMも送る
        if child.role == "reviewer" and context.get("code"):
            await child.send_dm(
                "coder",
                f"Code review feedback:\n{result_text}",
            )

        await child.complete_task(task_id, {"output": result_text})

    @child.on_message(MessageType.AGENT_DM)
    async def handle_dm(msg: AgentMessage):
        content = msg.payload.get("content", "")
        logger.info(f"[{child.agent_id}] DM from {msg.from_agent}: {content[:80]}")

    @child.on_message(MessageType.AGENT_BROADCAST)
    async def handle_broadcast(msg: AgentMessage):
        content = msg.payload.get("content", "")
        logger.info(f"[{child.agent_id}] Broadcast from {msg.from_agent}: {content[:80]}")


async def run_demo(launcher_type: str = "auto", port: int = 5570):
    """デモシナリオ実行"""
    total_steps = 9

    print(f"\n{C_BOLD}{C_MAGENTA}{'=' * 60}")
    print("  ZMQ Agent-to-Agent Communication PoC")
    print(f"  Code Review Workflow Demo")
    print(f"{'=' * 60}{C_RESET}\n")

    # --- Launcher選択 ---
    launcher: ChildLauncher
    if launcher_type == "auto":
        if shutil.which("tmux") and _in_tmux():
            launcher = TmuxPaneLauncher()
            log_info("Using TmuxPaneLauncher (tmux detected)")
        else:
            launcher = SubprocessLauncher()
            log_info("Using SubprocessLauncher (no tmux)")
    elif launcher_type == "tmux":
        launcher = TmuxPaneLauncher()
    elif launcher_type == "subprocess":
        launcher = SubprocessLauncher()
    elif launcher_type == "inprocess":
        launcher = InProcessLauncher()
        log_info("Using InProcessLauncher (single process, debug mode)")
    elif launcher_type == "aetherterm":
        server_url = os.environ.get("AGENTSERVER_URL", "ws://localhost:57575")
        aetherterm_launcher = AetherTermPaneLauncher(server_url=server_url)
        log_info(f"Using AetherTermPaneLauncher ({server_url})")
        log_info("Connecting to AgentServer...")
        await aetherterm_launcher.connect()
        launcher = aetherterm_launcher
        log_info(f"Connected! Session: {aetherterm_launcher._session_id}")
    else:
        raise ValueError(f"Unknown launcher: {launcher_type}")

    # --- Step 1: Start parent ---
    log_step(1, total_steps, "Starting ParentAgent (ZMQ ROUTER)")
    parent = ParentAgent(router_port=port, launcher=launcher)

    registered_agents = []

    def on_registered(agent_id, role):
        registered_agents.append(agent_id)
        log_result(agent_id, f"Registered (role={role})")

    parent.set_on_agent_registered(on_registered)
    await parent.start()
    log_info(f"ROUTER listening on tcp://*:{port}")

    try:
        # --- Step 2: Spawn 3 agents ---
        log_step(2, total_steps, "Spawning child agents: coder, reviewer, tester")
        agents = [
            ("coder", "coder"),
            ("reviewer", "reviewer"),
            ("tester", "tester"),
        ]
        for agent_id, role in agents:
            await parent.spawn_child(agent_id, role)
            log_info(f"Spawned {agent_id}")

        # Wait for all agents to register
        log_info("Waiting for agent registration...")
        for agent_id, _ in agents:
            ok = await parent.wait_for_agent(agent_id, timeout=15.0)
            if not ok:
                print(f"  {C_BOLD}✗ Failed to register {agent_id}{C_RESET}")
                return

        print(f"\n  {C_GREEN}All {len(agents)} agents registered!{C_RESET}")

        # --- Step 3: Task → coder ---
        log_step(3, total_steps, "Sending task to coder: 'Implement fibonacci function'")
        coder_future = await parent.send_task(
            "coder",
            task_type="implement",
            description="Implement fibonacci function",
            context={"language": "python"},
        )

        # --- Step 4: Wait for coder result ---
        log_step(4, total_steps, "Waiting for coder to complete...")
        coder_result = await asyncio.wait_for(coder_future, timeout=15.0)
        code = coder_result["result"].get("output", "")
        log_result("coder", f"Code generated ({len(code)} chars)")
        print(f"{C_DIM}")
        for line in code.strip().split("\n")[:6]:
            print(f"    {line}")
        print(f"{C_RESET}")

        # --- Step 5: Task → reviewer ---
        log_step(5, total_steps, "Sending task to reviewer: 'Review this code'")
        reviewer_future = await parent.send_task(
            "reviewer",
            task_type="review",
            description="Review this code",
            context={"code": code},
        )

        # --- Step 6: Wait for reviewer ---
        log_step(6, total_steps, "Waiting for reviewer...")
        reviewer_result = await asyncio.wait_for(reviewer_future, timeout=15.0)
        review = reviewer_result["result"].get("output", "")
        log_result("reviewer", "Review completed")
        print(f"{C_DIM}")
        for line in review.strip().split("\n")[:5]:
            print(f"    {line}")
        print(f"{C_RESET}")

        # Small delay for DM delivery (reviewer → coder)
        await asyncio.sleep(0.5)

        # --- Step 7: Task → tester ---
        log_step(7, total_steps, "Sending task to tester: 'Write tests for fibonacci'")
        tester_future = await parent.send_task(
            "tester",
            task_type="test",
            description="Write tests for fibonacci",
            context={"code": code},
        )

        # --- Step 8: Wait for tester ---
        log_step(8, total_steps, "Waiting for tester...")
        tester_result = await asyncio.wait_for(tester_future, timeout=15.0)
        tests = tester_result["result"].get("output", "")
        log_result("tester", f"Tests generated ({len(tests)} chars)")
        print(f"{C_DIM}")
        for line in tests.strip().split("\n")[:6]:
            print(f"    {line}")
        print(f"{C_RESET}")

        # --- Step 9: Broadcast + shutdown ---
        log_step(9, total_steps, "Broadcasting 'Workflow complete' + shutdown")
        await parent.broadcast("Workflow complete! All tasks finished successfully.")
        await asyncio.sleep(0.5)

        print(f"\n{C_BOLD}{C_GREEN}{'=' * 60}")
        print("  Demo Complete!")
        print(f"  - 3 agents spawned and registered")
        print(f"  - Task delegation: implement → review → test")
        print(f"  - DM: reviewer → coder (feedback)")
        print(f"  - Broadcast: parent → all (completion)")
        print(f"{'=' * 60}{C_RESET}\n")

    except asyncio.TimeoutError as e:
        print(f"\n  {C_BOLD}✗ Timeout: {e}{C_RESET}")
    except Exception as e:
        print(f"\n  {C_BOLD}✗ Error: {e}{C_RESET}")
        logger.exception("Demo error")
    finally:
        await parent.stop()
        if launcher_type == "aetherterm" and isinstance(launcher, AetherTermPaneLauncher):
            await launcher.disconnect()
            log_info("Disconnected from AgentServer")
        log_info("ParentAgent stopped. Cleanup complete.")


def _in_tmux() -> bool:
    """tmuxセッション内かどうかを判定"""
    return bool(os.environ.get("TMUX"))


def main():
    parser = argparse.ArgumentParser(
        description="ZMQ Agent Communication PoC - Code Review Workflow Demo"
    )
    parser.add_argument(
        "--launcher",
        choices=["auto", "tmux", "subprocess", "inprocess", "aetherterm"],
        default="auto",
        help="Child launcher type (default: auto-detect). "
        "aetherterm: creates panes in AgentServer (requires running AgentServer)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5570,
        help="ZMQ ROUTER port (default: 5570)",
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
    # Suppress noisy loggers
    if not args.verbose:
        logging.getLogger("aetherterm").setLevel(logging.WARNING)

    asyncio.run(run_demo(launcher_type=args.launcher, port=args.port))


if __name__ == "__main__":
    main()

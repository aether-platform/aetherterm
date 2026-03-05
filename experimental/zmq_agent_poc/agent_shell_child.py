"""AgentShellChild — ChildAgent + claude CLI execution

AgentShell相当: ZMQ DEALERで親ROUTERに接続しつつ、
タスク受信時に `claude -p` を実行してAI処理を行う。

アーキテクチャ:
    Parent (ROUTER)
        ↓ ZMQ
    AgentShellChild (DEALER + claude subprocess)
        ↓ subprocess
    claude CLI (`claude -p "prompt"`)

Usage (standalone):
    python -m experimental.zmq_agent_poc.agent_shell_child \
        --agent-id coder --role coder --router tcp://localhost:5570

Usage (in code):
    agent = AgentShellChild("coder", "coder", workspace="/tmp/workspace")
    agent.on_task(handle_task)
    await agent.start()
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
import tempfile
import time
from typing import Any, Dict, Optional

from aetherterm.common.agent_protocol import AgentMessage, MessageType

from .child_agent import ChildAgent

logger = logging.getLogger(__name__)

# ANSI colors
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_BLUE = "\033[34m"
C_CYAN = "\033[36m"
C_RED = "\033[31m"


# Role → system prompt template
ROLE_PROMPTS: Dict[str, str] = {
    "coder": (
        "You are an expert software engineer. "
        "Write clean, well-documented, production-quality code. "
        "Include docstrings and type hints. "
        "Output ONLY the code, no explanations unless asked."
    ),
    "reviewer": (
        "You are an expert code reviewer. "
        "Analyze code for bugs, security issues, performance problems, and style. "
        "Be constructive and specific. Format as a structured review with "
        "sections: Summary, Issues Found, Suggestions, Verdict (APPROVE/REQUEST_CHANGES)."
    ),
    "tester": (
        "You are an expert test engineer. "
        "Write comprehensive pytest test cases with edge cases, "
        "boundary conditions, and error scenarios. "
        "Include docstrings explaining what each test verifies."
    ),
    "architect": (
        "You are an expert software architect. "
        "Analyze system design, suggest improvements, "
        "identify architectural concerns, and propose solutions."
    ),
}


class AgentShellChild(ChildAgent):
    """AgentShell + ZMQ DEALER + claude execution

    ChildAgentのZMQ通信層に加え、タスク受信時に `claude -p` を
    subprocess実行してAI処理を行う。tmux paneで視覚的に
    claudeの動作が確認できる。
    """

    def __init__(
        self,
        agent_id: str,
        role: str,
        router_addr: str = "tcp://localhost:5570",
        workspace: Optional[str] = None,
        claude_model: Optional[str] = None,
        timeout: float = 120.0,
        use_claude: bool = True,
    ):
        super().__init__(agent_id, role, router_addr)
        self._workspace = workspace
        self._claude_model = claude_model
        self._timeout = timeout
        self._use_claude = use_claude and bool(shutil.which("claude"))
        self._execution_count = 0

        if use_claude and not self._use_claude:
            logger.warning(
                f"[{agent_id}] claude CLI not found, falling back to stubs"
            )

    @property
    def workspace(self) -> Optional[str]:
        return self._workspace

    # --- Override think() ---

    async def think(self, prompt: str) -> str:
        """AI処理: claude -p で実行（fallback: stub応答）"""
        if self._use_claude:
            return await self._run_claude(prompt)
        return await super().think(prompt)

    # --- claude execution ---

    async def _run_claude(self, prompt: str) -> str:
        """claude -p を実行して結果をキャプチャ

        1. role-specific system prompt を付与
        2. claude -p でnon-interactive実行
        3. stdout/stderr をキャプチャ
        4. 画面にも出力（tmux paneで視覚確認用）
        """
        self._execution_count += 1
        system_prompt = ROLE_PROMPTS.get(self._role, "")

        # Build full prompt with role context
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n---\n\n{prompt}"

        # Build command
        cmd = ["claude", "-p", full_prompt]
        if self._claude_model:
            cmd.extend(["--model", self._claude_model])

        # Print header (visible in tmux pane)
        self._print_banner(
            f"claude #{self._execution_count}",
            f"role={self._role}, model={self._claude_model or 'default'}",
        )
        self._print_section("Prompt", prompt, max_lines=5)

        start = time.time()

        try:
            # Build env: unset CLAUDECODE to allow nested claude execution
            env = {
                k: v
                for k, v in os.environ.items()
                if k != "CLAUDECODE"
            }
            env["AGENT_ID"] = self._agent_id
            env["AGENT_ROLE"] = self._role

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._workspace,
                env=env,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )

            elapsed = time.time() - start
            result = stdout_bytes.decode("utf-8", errors="replace").strip()
            stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                error_msg = stderr or f"claude exited with code {proc.returncode}"
                self._print_error(error_msg)
                logger.error(f"[{self._agent_id}] claude failed: {error_msg}")
                return f"ERROR: {error_msg}"

            # Print result (visible in pane)
            self._print_section("Output", result, max_lines=20)
            self._print_footer(elapsed)

            logger.info(
                f"[{self._agent_id}] claude completed in {elapsed:.1f}s "
                f"({len(result)} chars)"
            )
            return result

        except asyncio.TimeoutError:
            elapsed = time.time() - start
            self._print_error(f"Timeout after {elapsed:.1f}s")
            logger.error(f"[{self._agent_id}] claude timed out after {elapsed:.1f}s")
            # Kill the process
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return f"ERROR: claude timed out after {elapsed:.1f}s"

        except Exception as e:
            self._print_error(str(e))
            logger.error(f"[{self._agent_id}] claude error: {e}")
            return f"ERROR: {e}"

    # --- Console output helpers (visible in tmux pane) ---

    def _print_banner(self, title: str, subtitle: str = "") -> None:
        width = 60
        print(f"\n{C_CYAN}{'━' * width}")
        print(f"  {C_BOLD}[{self._agent_id}] {title}{C_RESET}{C_CYAN}")
        if subtitle:
            print(f"  {C_DIM}{subtitle}{C_RESET}{C_CYAN}")
        print(f"{'━' * width}{C_RESET}")

    def _print_section(self, label: str, text: str, max_lines: int = 10) -> None:
        lines = text.strip().split("\n")
        print(f"\n  {C_YELLOW}{label}:{C_RESET}")
        for line in lines[:max_lines]:
            print(f"  {C_DIM}│{C_RESET} {line}")
        if len(lines) > max_lines:
            print(f"  {C_DIM}│ ... ({len(lines) - max_lines} more lines){C_RESET}")

    def _print_footer(self, elapsed: float) -> None:
        print(f"\n  {C_GREEN}✓ Completed in {elapsed:.1f}s{C_RESET}")
        print(f"{C_CYAN}{'━' * 60}{C_RESET}\n")

    def _print_error(self, msg: str) -> None:
        print(f"\n  {C_RED}✗ Error: {msg}{C_RESET}")
        print(f"{C_CYAN}{'━' * 60}{C_RESET}\n")


# --- CLI Entry Point ---

async def run_agent_shell(
    agent_id: str,
    role: str,
    router_addr: str,
    workspace: Optional[str] = None,
    claude_model: Optional[str] = None,
    use_claude: bool = True,
):
    """AgentShellChildをスタンドアロン起動"""
    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s [{agent_id}] %(levelname)s: %(message)s",
    )

    agent = AgentShellChild(
        agent_id=agent_id,
        role=role,
        router_addr=router_addr,
        workspace=workspace,
        claude_model=claude_model,
        use_claude=use_claude,
    )

    # Default task handler: think → complete
    @agent.on_message(MessageType.TASK_CREATE)
    async def handle_task(msg: AgentMessage):
        task_id = msg.payload.get("task_id")
        description = msg.payload.get("description", "")
        context = msg.payload.get("context", {})

        # Build prompt from task
        prompt = description
        if context.get("code"):
            prompt += f"\n\nCode to review/test:\n```\n{context['code']}\n```"
        if context.get("files"):
            prompt += f"\n\nRelevant files: {', '.join(context['files'])}"

        logger.info(f"Processing task: {description[:80]}")
        result_text = await agent.think(prompt)

        # reviewer sends DM to coder
        if role == "reviewer" and context.get("code"):
            await agent.send_dm(
                "coder",
                f"Code review feedback:\n{result_text}",
            )

        await agent.complete_task(task_id, {"output": result_text})

    # Default DM handler
    @agent.on_message(MessageType.AGENT_DM)
    async def handle_dm(msg: AgentMessage):
        content = msg.payload.get("content", "")
        logger.info(f"DM from {msg.from_agent}: {content[:80]}")

    # Default broadcast handler
    @agent.on_message(MessageType.AGENT_BROADCAST)
    async def handle_broadcast(msg: AgentMessage):
        content = msg.payload.get("content", "")
        logger.info(f"Broadcast from {msg.from_agent}: {content[:80]}")

    await agent.start()

    try:
        while agent.is_running:
            await asyncio.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        await agent.stop()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="AgentShellChild - ZMQ DEALER + claude")
    parser.add_argument("--agent-id", default=os.environ.get("AGENT_ID", "shell-1"))
    parser.add_argument("--role", default=os.environ.get("AGENT_ROLE", "coder"))
    parser.add_argument(
        "--router", default=os.environ.get("AGENT_ROUTER", "tcp://localhost:5570")
    )
    parser.add_argument("--workspace", default=os.environ.get("AGENT_WORKSPACE"))
    parser.add_argument("--model", default=None, help="Claude model to use")
    parser.add_argument(
        "--no-claude", action="store_true", help="Use stubs instead of claude"
    )
    args = parser.parse_args()

    asyncio.run(
        run_agent_shell(
            agent_id=args.agent_id,
            role=args.role,
            router_addr=args.router,
            workspace=args.workspace,
            claude_model=args.model,
            use_claude=not args.no_claude,
        )
    )


if __name__ == "__main__":
    main()

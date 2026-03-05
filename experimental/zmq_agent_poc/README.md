# ZMQ Agent-to-Agent Communication PoC

AI Agent間の直接通信基盤PoC。親プロセス(AgentServer相当)がZMQ ROUTERとして動作し、子プロセス(AgentShell相当)をpaneで起動してDEALER接続する。

## Architecture

```
┌─────────────────────────────────────┐
│  ParentAgent (Orchestrator)         │
│  ZMQ ROUTER :5570                   │
│  - Agent Registry (who's connected) │
│  - Message Routing (DM/Broadcast)   │
│  - Child Lifecycle Management       │
└──────┬──────────┬──────────┬────────┘
       │ DEALER   │ DEALER   │ DEALER
┌──────┴───┐ ┌────┴─────┐ ┌─┴────────┐
│ coder    │ │ reviewer │ │ tester   │
│ (pane)   │ │ (pane)   │ │ (pane)   │
└──────────┘ └──────────┘ └──────────┘
```

## Quick Start

### Stub Demo (AI stub応答、claude不要)

```bash
cd /mnt/c/workspace/vibecoding-platform/app/terminal

# In-process mode (シングルプロセス、最も手軽)
python -m experimental.zmq_agent_poc.run_demo --launcher inprocess

# Subprocess mode (tmuxなし)
python -m experimental.zmq_agent_poc.run_demo --launcher subprocess

# Tmux mode (tmux内で実行)
python -m experimental.zmq_agent_poc.run_demo --launcher tmux

# AetherTerm mode (AgentServer経由でペーン作成)
# 事前に make run-agentserver でAgentServerを起動し、ブラウザで開いておく
python -m experimental.zmq_agent_poc.run_demo --launcher aetherterm

# Auto-detect (tmux内ならtmux、そうでなければsubprocess)
python -m experimental.zmq_agent_poc.run_demo

# Debug logging
python -m experimental.zmq_agent_poc.run_demo --launcher inprocess -v
```

### Claude Demo (実際のclaude CLIでAI処理)

```bash
# In-process + Claude CLI
python -m experimental.zmq_agent_poc.run_claude_demo

# Dry-run (claude不使用、stub応答)
python -m experimental.zmq_agent_poc.run_claude_demo --dry-run

# AetherTerm pane + Claude CLI (ブラウザ上でペーンが作成される)
python -m experimental.zmq_agent_poc.run_claude_demo --launcher aetherterm

# カスタムworkspace / model / timeout
python -m experimental.zmq_agent_poc.run_claude_demo \
    --workspace /tmp/my_workspace \
    --model claude-sonnet-4-6 \
    --timeout 180
```

## Demo Scenario: Code Review Workflow

1. **Parent** spawns 3 agents: `coder`, `reviewer`, `tester`
2. **Parent → coder**: `TASK_CREATE` "Implement fibonacci function"
3. **coder**: generates code → `TASK_COMPLETE`
4. **Parent → reviewer**: `TASK_CREATE` "Review this code"
5. **reviewer**: Reviews → sends **DM** to coder with feedback
6. **coder**: Receives DM
7. **Parent → tester**: `TASK_CREATE` "Write tests"
8. **tester**: `TASK_COMPLETE` with tests
9. **Parent**: **Broadcast** "Workflow complete" → shutdown all

## Wire Format

ZMQ multipart frames over ROUTER/DEALER:

```
Parent recv: [dealer_identity, msgpack(AgentMessage.to_dict())]
Parent send: [dealer_identity, msgpack(AgentMessage.to_dict())]
Child  recv: [msgpack(AgentMessage.to_dict())]
Child  send: [msgpack(AgentMessage.to_dict())]
```

Uses `pack_message()` / `unpack_message()` from `aetherterm.common.zmq_utils`.

## Files

| File | Description |
|------|-------------|
| `parent_agent.py` | ZMQ ROUTER host + agent registry + message routing |
| `child_agent.py` | ZMQ DEALER client + message handler + AI stub |
| `agent_shell_child.py` | AgentShellChild: ChildAgent + claude CLI execution |
| `child_launcher.py` | Abstraction layer: tmux / subprocess / inprocess / AetherTerm |
| `run_demo.py` | Stub demo: 3-agent code review workflow |
| `run_claude_demo.py` | Claude demo: real claude CLI for AI processing |

## Reused Modules

| Module | Path |
|--------|------|
| `AgentMessage` / `MessageType` | `src/aetherterm/common/agent_protocol.py` |
| `MessageBuilder` | same |
| `pack_message` / `unpack_message` | `src/aetherterm/common/zmq_utils.py` |
| `safe_create_task` | same |

## Launcher Types

| Type | CLI flag | Description | 要件 |
|------|----------|-------------|------|
| `InProcessLauncher` | `inprocess` | asyncio.create_task (シングルプロセス) | なし |
| `SubprocessLauncher` | `subprocess` | asyncio.subprocess (バックグラウンド) | なし |
| `TmuxPaneLauncher` | `tmux` | tmux split-window (視覚的ペーン) | tmux内 |
| `AetherTermPaneLauncher` | `aetherterm` | AgentServer WebSocket経由でペーン作成 | AgentServer起動 + ブラウザ |

## Standalone Components

```bash
# ROUTER単体起動
python -m experimental.zmq_agent_poc.parent_agent --port 5570

# DEALER単体起動 (stub)
python -m experimental.zmq_agent_poc.child_agent \
    --agent-id coder --role coder --router tcp://localhost:5570

# DEALER単体起動 (claude CLI)
python -m experimental.zmq_agent_poc.agent_shell_child \
    --agent-id coder --role coder --router tcp://localhost:5570 \
    --workspace /tmp/workspace

# DEALER単体起動 (claude CLIなし、stub)
python -m experimental.zmq_agent_poc.agent_shell_child \
    --agent-id coder --role coder --router tcp://localhost:5570 --no-claude
```

## AetherTerm Pane Integration

`--launcher aetherterm` を使うと、AgentServerの `split_pane` APIを通じて
ブラウザ上にPTYペーンが作成される。各ペーンで子Agentが実行され、
ブラウザから視覚的にAgent動作を確認可能。

```bash
# 1. AgentServerを起動
make run-agentserver

# 2. ブラウザで http://localhost:57575 を開く

# 3. デモ実行 (ブラウザにペーンが追加される)
python -m experimental.zmq_agent_poc.run_claude_demo --launcher aetherterm

# 環境変数でAgentServerのURLを指定可能
AGENTSERVER_URL=ws://custom-host:57575 \
    python -m experimental.zmq_agent_poc.run_claude_demo --launcher aetherterm
```

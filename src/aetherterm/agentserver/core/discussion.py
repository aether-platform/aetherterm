"""Multi-Agent Discussion prompt builder.

Builds the orchestration prompt that Parent Claude receives
to autonomously spawn sub-agents, assign roles, drive discussion rounds,
and write summaries.

Usage from routes:
    from .discussion import build_discussion_prompt
    prompt = build_discussion_prompt(topic=topic, scale=scale, role=role)
"""
# ruff: noqa: E501 — prompt template lines are intentionally long

from __future__ import annotations

import argparse
import sys

DEFAULT_AGENTS = ["claude", "gemini", "codex", "opencode"]


def build_discussion_prompt(
    topic: str,
    scale: str = "le",
    role: str = "both",
    agents: list[str] | None = None,
    session_id: str = "",
) -> str:
    """Build the orchestration prompt for parent Claude.

    Args:
        topic: Discussion topic
        scale: "sme" or "le" (default)
        role: "both", "biz", or "dev" (default: "both")
        agents: Optional list of agent types to use.
        session_id: Tmux session ID for API calls.
    """
    if agents is None:
        agents = DEFAULT_AGENTS

    scale = (scale or "le").lower()
    role = (role or "both").lower()

    # Scale-dependent instructions
    if scale == "sme":
        scale_instruction = """## Scale: SME (Small / Medium)
少人数チーム・スタートアップ向けの議論スケールです。
エージェント数は最小限（2-3体）にし、一人が複数の視点をカバーします。
迅速な意思決定とリーンな実行を重視してください。

### Role Assignment
- 各エージェントにTechとBusiness両方の視点を持たせる
- 専門分化より汎用性を優先

### Schedule Guideline
- **Tech提案**: スケジュールを長引かせがちな傾向あり。各提案に必ず
  **短縮案（Pragmatic Alternative）** を併記すること。
  80%の価値を短期で届けるMVPアプローチを常に意識。
- **Business提案**: スケジュールを詰めがちな傾向あり。
  提案を **短期目標（Quick Wins: 1-2週間）** と **中期目標（Strategic: 1-3ヶ月）** に
  分けて提示すること。技術的負債を生まない現実的な計画を心がける。
- サマリーでは実行可能な **統合ロードマップ** を含めること。"""
    else:  # le (default)
        scale_instruction = """## Scale: LE (Large Enterprise)
大規模組織・マルチチーム向けの議論スケールです。
エージェントを多く（4体以上）活用し、専門的な視点を分担させます。
ガバナンス、コンプライアンス、組織横断の調整を考慮してください。

### Role Assignment
- Business担当とTech担当を明確に分離する
- 必要に応じてセキュリティ、コンプライアンス、PMO等の専門ロールを追加
- サマリーではTechとBusinessを明確に分けたセクション構成にすること

### Schedule Guideline
- **Tech担当エージェント**: スケジュールを長引かせがちな傾向があるため、
  各提案に **短縮案（Pragmatic Alternative）** を併記すること。
  80%の価値を短期で届けるMVPアプローチを常に意識。
- **Business担当エージェント**: スケジュールを詰めがちな傾向があるため、
  提案を **短期目標（Quick Wins: 1-2週間）** と **中期目標（Strategic: 1-3ヶ月）** に
  分けて提示すること。技術的負債を生まない現実的な計画を心がける。
- 最終サマリーでは、Tech/Business双方のスケジュール感を擦り合わせた
  **統合ロードマップ** を含めること。"""

    # Role-dependent instructions
    if role == "biz":
        role_instruction = """## Role Focus: Biz (Business)
ビジネス観点に集中した議論を行います。
市場インパクト、ROI、ユーザー体験、競合分析、Go-to-Market戦略、組織影響を重視。
エージェントにはPM、BA、UXストラテジスト等のビジネスロールを割り当ててください。"""
    elif role == "dev":
        role_instruction = """## Role Focus: Dev (Technical)
技術観点に集中した議論を行います。
アーキテクチャ、パフォーマンス、スケーラビリティ、セキュリティ、DX、テスト戦略を重視。
エージェントにはアーキテクト、SRE、セキュリティエンジニア等の技術ロールを割り当ててください。"""
    else:  # both
        role_instruction = """## Role Focus: Both (Cross-functional)
ビジネスと技術の両面を網羅する議論を行います。
エージェントにBiz担当とDev担当を分けて割り当て、サマリーでは
**Biz視点** と **Dev視点** を明確に分離したセクション構成にしてください。"""

    agent_cli_list = "\n".join(
        f"- `{a}` -- {_agent_description(a)}" for a in agents
    )

    return f"""You are the orchestrator (Parent agent) of a multi-agent discussion.
You have full autonomy to spawn agents, assign roles, direct the conversation, and synthesize results.

## Discussion Topic
{topic}

{scale_instruction}

{role_instruction}

## Process Overview
1. **Setup** -- エージェント起動 + 役割定義
2. **Round 1** -- 各ロールからトピックに対する初期提案を収集
3. **Round 2+** -- 相互レビュー、深掘り、対案
4. **Summary** -- 最終統合レポート

## Phase 1: Setup -- エージェント起動と役割定義

### 1-1. Spawn Sub-agents
Available agent CLIs:
{agent_cli_list}

Spawn each agent using tmux. Use the native CLI for each agent type:

For **claude**:
```bash
tmux new-window -n "<role>:claude-1" "claude --dangerously-skip-permissions --teammate-mode tmux"
```

For **other agents** (gemini, codex, opencode):
```bash
tmux new-window -n "<role>:<agent_type>-1" "{sys.executable} -m aetherterm.agentshell.main --agent-id <agent_type>-1 --role <role> --agent-type <agent_type>"
```

Choose agent count based on scale. Wait 5-10 seconds for initialization.

### 1-2. 役割定義
Run `tmux list-panes -a` to find pane IDs.
**先にロールだけを伝える（トピックへの提案はまだ求めない）:**
```bash
tmux send-keys -t <pane_id> "あなたの役割は【ロール名】です。担当領域は【担当領域の説明】です。次の指示を待ってください。" Enter
```
全エージェントにロールが行き渡ったことを確認してから次に進む。

## Phase 2: Round 1 -- 初期提案

各エージェントにトピックを送り、**各ロールの視点から提案**を求める:
```bash
tmux send-keys -t <pane_id> "以下のトピックについて、あなたのロール【ロール名】の観点から提案してください: {topic}" Enter
```

Wait 30-60s, then read each agent's output:
```bash
tmux capture-pane -t <pane_id> -p
```

Round 1 結果をサマリーに記録.

## Phase 3: Round 2+ -- 深掘りと相互レビュー

Round 1 の結果を踏まえて:
- 他のロールの提案を共有し、意見・反論を求める
- 具体例やデータによる裏付けを要求
- 対立点の解消案を提示させる

各ラウンド終了後にサマリーを記録。2-3 ラウンドが目安。

## Phase 4: Final Synthesis

Write the final summary with:
- 全ロールの視点を統合した結論
- 各提案のエージェント帰属
- 実行可能なアクションアイテム
- 未解決の論点
{"- **Biz と Dev のセクションを明確に分離**" if role == "both" else ""}

## Rules
- 役割定義を先に行い、提案はRound 1で改めて求める
- Use tmux capture-pane for reading agent output
- Attribute all insights to the originating agent
- Aim for 2-3 discussion rounds before final synthesis
- Keep send-keys messages concise but clear

Begin now.
"""


def _agent_description(agent_type: str) -> str:
    descs = {
        "gemini": "Google Gemini CLI",
        "codex": "OpenAI Codex CLI",
        "opencode": "OpenCode (multi-provider)",
        "claude": "Claude Code (Anthropic)",
    }
    return descs.get(agent_type, agent_type)


# ---------------------------------------------------------------------------
# Debug CLI
# ---------------------------------------------------------------------------

def main():
    """Debug CLI: preview the orchestration prompt that would be sent."""
    parser = argparse.ArgumentParser(
        description="Preview discussion prompt (debug/validation tool)"
    )
    parser.add_argument("--topic", required=True, help="Discussion topic")
    parser.add_argument("--scale", default="le", choices=["sme", "le"])
    parser.add_argument("--role", default="both", choices=["both", "biz", "dev"])
    parser.add_argument("--agents", nargs="+", default=None,
                        choices=["gemini", "codex", "opencode", "claude"])
    args = parser.parse_args()

    prompt = build_discussion_prompt(
        topic=args.topic, scale=args.scale, role=args.role, agents=args.agents,
    )
    print(prompt)
    print(f"\n--- {len(prompt)} chars ---")


if __name__ == "__main__":
    main()

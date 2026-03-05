#!/usr/bin/env python3
"""LangChain + OpenHands統合デモ

LangChainエージェントがメモリ管理・コンテキスト保持を行いながら、
OpenHandsエージェントにコード生成タスクを委譲する動作を実証します。
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from ...common.agent_protocol import (
    InterventionData,
    InterventionType,
    ProgressData,
    TaskData,
)
from ..agents import AgentManager, LangChainAgent

# ログ設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class LangChainOpenHandsDemo:
    """LangChain + OpenHands統合デモクラス"""

    def __init__(self):
        self.agent_manager = AgentManager()

        # エージェントID
        self.langchain_agent_id = f"langchain_{uuid4().hex[:8]}"
        self.openhands_agent_id = f"openhands_{uuid4().hex[:8]}"

        # 実行履歴
        self.execution_history: List[Dict] = []

    async def setup(self):
        """デモ環境をセットアップ"""
        logger.info("デモ環境をセットアップ中...")

        # LangChainエージェントを作成
        langchain_agent = LangChainAgent(
            agent_id=self.langchain_agent_id, agent_manager=self.agent_manager
        )

        # 進捗コールバックを設定
        langchain_agent.set_progress_callback(self._on_progress)
        langchain_agent.set_intervention_callback(self._on_intervention)

        # エージェントを登録
        self.agent_manager.register_agent(langchain_agent)

        # エージェントを開始
        await self.agent_manager.start_agent(self.langchain_agent_id)

        logger.info("デモ環境のセットアップが完了しました")

    async def teardown(self):
        """デモ環境をクリーンアップ"""
        logger.info("デモ環境をクリーンアップ中...")

        # すべてのエージェントを停止
        for agent_id in self.agent_manager.list_agents():
            await self.agent_manager.stop_agent(agent_id)

        logger.info("デモ環境のクリーンアップが完了しました")

    def _on_progress(self, progress: ProgressData):
        """進捗通知を処理"""
        logger.info(
            f"[進捗] タスク {progress.task_id}: "
            f"{progress.percentage * 100:.1f}% - {progress.message}"
        )

        self.execution_history.append(
            {
                "type": "progress",
                "task_id": progress.task_id,
                "percentage": progress.percentage,
                "message": progress.message,
                "timestamp": datetime.now().isoformat(),
            }
        )

    async def _on_intervention(self, intervention: InterventionData) -> Optional[str]:
        """ユーザー介入を処理"""
        logger.info(f"[介入要求] {intervention.message}")

        self.execution_history.append(
            {
                "type": "intervention",
                "intervention_type": intervention.type,
                "message": intervention.message,
                "timestamp": datetime.now().isoformat(),
            }
        )

        # デモなので自動的に承認
        if intervention.type == InterventionType.APPROVAL:
            logger.info("→ 自動承認")
            return "approved"
        if intervention.type == InterventionType.CHOICE:
            choice = intervention.options[0] if intervention.options else "default"
            logger.info(f"→ 自動選択: {choice}")
            return choice
        return "default_response"

    async def run_scenario_1_simple_code_generation(self):
        """シナリオ1: シンプルなコード生成"""
        print("\n" + "=" * 60)
        print("シナリオ1: シンプルなコード生成")
        print("=" * 60)
        print("LangChainがコンテキストを管理し、OpenHandsがコードを生成します")
        print("-" * 60)

        # タスクを作成
        task = TaskData(
            task_id=f"task_{uuid4().hex[:8]}",
            task_type="code_generation",
            description="Pythonで簡単なTODOリストアプリケーションを作成してください",
            parameters={
                "language": "python",
                "framework": "FastAPI",
                "features": ["CRUD操作", "SQLiteデータベース", "REST API"],
            },
            priority=1,
        )

        # タスクを実行
        logger.info(f"\nタスクを実行: {task.description}")
        result = await self.agent_manager.execute_task(self.langchain_agent_id, task)

        # 結果を表示
        print("\n実行結果:")
        print(f"- ステータス: {result.get('status', 'unknown')}")
        print(f"- 生成されたコード: {len(result.get('code', ''))} 文字")

        return result

    async def run_scenario_2_context_aware_refactoring(self):
        """シナリオ2: コンテキスト認識リファクタリング"""
        print("\n" + "=" * 60)
        print("シナリオ2: コンテキスト認識リファクタリング")
        print("=" * 60)
        print("過去の会話履歴を考慮したリファクタリング")
        print("-" * 60)

        # まず分析タスクを実行（コンテキストを蓄積）
        analysis_task = TaskData(
            task_id=f"task_{uuid4().hex[:8]}",
            task_type="analyze",
            description="既存のコードベースを分析し、改善点を特定してください",
            parameters={"focus_areas": ["パフォーマンス", "可読性", "保守性"]},
            priority=1,
        )

        logger.info(f"\n分析タスクを実行: {analysis_task.description}")
        analysis_result = await self.agent_manager.execute_task(
            self.langchain_agent_id, analysis_task
        )

        # リファクタリングタスクを実行（前の分析結果を活用）
        refactor_task = TaskData(
            task_id=f"task_{uuid4().hex[:8]}",
            task_type="refactoring",
            description="分析結果に基づいてコードをリファクタリングしてください",
            parameters={"target_improvements": analysis_result.get("recommendations", [])},
            priority=1,
        )

        logger.info(f"\nリファクタリングタスクを実行: {refactor_task.description}")
        refactor_result = await self.agent_manager.execute_task(
            self.langchain_agent_id, refactor_task
        )

        # 結果を表示
        print("\n実行結果:")
        print("1. 分析結果:")
        print(f"   - 特定された問題: {len(analysis_result.get('recommendations', []))}件")
        print("2. リファクタリング結果:")
        print(f"   - ステータス: {refactor_result.get('status', 'unknown')}")

        return {"analysis": analysis_result, "refactoring": refactor_result}

    async def run_scenario_3_multi_step_development(self):
        """シナリオ3: マルチステップ開発フロー"""
        print("\n" + "=" * 60)
        print("シナリオ3: マルチステップ開発フロー")
        print("=" * 60)
        print("要件定義 → 設計 → 実装 → テスト → ドキュメント作成")
        print("-" * 60)

        tasks = [
            TaskData(
                task_id=f"task_{uuid4().hex[:8]}",
                task_type="analyze",
                description="ユーザー管理システムの要件を分析してください",
                parameters={"system_type": "user_management"},
                priority=1,
            ),
            TaskData(
                task_id=f"task_{uuid4().hex[:8]}",
                task_type="code_generation",
                description="ユーザー管理システムのAPIを実装してください",
                parameters={"based_on": "previous_analysis"},
                priority=2,
            ),
            TaskData(
                task_id=f"task_{uuid4().hex[:8]}",
                task_type="testing",
                description="実装したAPIのテストコードを作成してください",
                parameters={"test_framework": "pytest"},
                priority=3,
            ),
            TaskData(
                task_id=f"task_{uuid4().hex[:8]}",
                task_type="documentation",
                description="APIドキュメントを作成してください",
                parameters={"format": "OpenAPI"},
                priority=4,
            ),
        ]

        results = []
        for i, task in enumerate(tasks, 1):
            logger.info(f"\nステップ {i}/{len(tasks)}: {task.description}")
            result = await self.agent_manager.execute_task(self.langchain_agent_id, task)
            results.append(result)

            # 各ステップの結果を表示
            print(f"   → 完了: {result.get('status', 'unknown')}")

        print("\n全体の実行結果:")
        print(f"- 完了したステップ: {len(results)}/{len(tasks)}")
        print("- コンテキスト活用: LangChainが各ステップの結果を記憶し、次のステップで活用")

        return results

    async def run_demo(self):
        """デモを実行"""
        try:
            await self.setup()

            # シナリオ1: シンプルなコード生成
            await self.run_scenario_1_simple_code_generation()
            await asyncio.sleep(2)

            # シナリオ2: コンテキスト認識リファクタリング
            await self.run_scenario_2_context_aware_refactoring()
            await asyncio.sleep(2)

            # シナリオ3: マルチステップ開発フロー
            await self.run_scenario_3_multi_step_development()

            # 実行履歴のサマリーを表示
            self._print_execution_summary()

        finally:
            await self.teardown()

    def _print_execution_summary(self):
        """実行履歴のサマリーを表示"""
        print("\n" + "=" * 60)
        print("実行履歴サマリー")
        print("=" * 60)

        # イベントタイプ別に集計
        event_counts = {}
        for event in self.execution_history:
            event_type = event["type"]
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

        print("イベント統計:")
        for event_type, count in event_counts.items():
            print(f"- {event_type}: {count}件")

        print(f"\n総イベント数: {len(self.execution_history)}")

        # LangChainとOpenHandsの連携を強調
        print("\n連携のポイント:")
        print("1. LangChainがコンテキストとメモリを管理")
        print("2. コード生成・編集タスクは自動的にOpenHandsに委譲")
        print("3. 結果はLangChainのメモリに保存され、後続タスクで活用")
        print("4. ユーザー介入ポイントは親エージェントが一元管理")


async def main():
    """メイン関数"""
    print("LangChain + OpenHands 統合デモ")
    print("================================")
    print("\nこのデモでは、LangChainエージェントがメモリ管理とコンテキスト保持を行い、")
    print("必要に応じてOpenHandsエージェントにタスクを委譲する様子を実演します。")

    demo = LangChainOpenHandsDemo()
    await demo.run_demo()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nデモが中断されました。")
    except Exception as e:
        print(f"\nエラーが発生しました: {e}")
        import traceback

        traceback.print_exc()

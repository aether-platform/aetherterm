"""エージェントマネージャー

複数のAIエージェントを管理し、タスクの割り当て、実行監視、
ユーザー介入の調整を行います。
"""

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import UUID

from .base import (
    AgentCapability,
    AgentInterface,
    AgentResult,
    AgentTask,
    TaskStatus,
    UserIntervention,
)
from .openhands import OpenHandsAgent

logger = logging.getLogger(__name__)


class AgentManager:
    """エージェントマネージャー

    複数のAIエージェントを統合管理し、タスクの適切な割り当て、
    実行監視、ユーザー介入の調整を行います。
    """

    def __init__(self):
        self._agents: Dict[str, AgentInterface] = {}
        self._capability_map: Dict[AgentCapability, Set[str]] = defaultdict(set)
        self._running_tasks: Dict[UUID, str] = {}  # task_id -> agent_id
        self._task_queue: asyncio.Queue[AgentTask] = asyncio.Queue()
        self._is_running = False
        self._worker_task: Optional[asyncio.Task] = None

        # コールバック
        self._intervention_callbacks: List[Callable[[UserIntervention, str], None]] = []
        self._progress_callbacks: List[Callable[[UUID, float, str, str], None]] = []
        self._completion_callbacks: List[Callable[[UUID, AgentResult], None]] = []

    async def start(self) -> None:
        """エージェントマネージャーを開始"""
        if self._is_running:
            return

        logger.info("エージェントマネージャーを開始します")
        self._is_running = True

        # ワーカータスクを開始
        self._worker_task = asyncio.create_task(self._task_worker())

    async def stop(self) -> None:
        """エージェントマネージャーを停止"""
        if not self._is_running:
            return

        logger.info("エージェントマネージャーを停止します")
        self._is_running = False

        # ワーカータスクを停止
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        # すべてのエージェントをシャットダウン
        shutdown_tasks = []
        for agent in self._agents.values():
            shutdown_tasks.append(agent.shutdown())

        if shutdown_tasks:
            await asyncio.gather(*shutdown_tasks, return_exceptions=True)

        self._agents.clear()
        self._capability_map.clear()
        self._running_tasks.clear()

    async def register_agent(
        self, agent: AgentInterface, config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """エージェントを登録

        Args:
            agent: 登録するエージェント
            config: エージェントの設定

        Returns:
            bool: 登録が成功した場合True
        """
        try:
            # エージェントを初期化
            if not await agent.initialize(config or {}):
                logger.error(f"エージェント {agent.agent_id} の初期化に失敗しました")
                return False

            # エージェントを登録
            self._agents[agent.agent_id] = agent

            # 能力マップを更新
            for capability in agent.get_capabilities():
                self._capability_map[capability].add(agent.agent_id)

            # コールバックを設定
            agent.register_intervention_callback(
                lambda ui: self._handle_agent_intervention(agent.agent_id, ui)
            )
            agent.register_progress_callback(
                lambda tid, prog, msg: self._handle_agent_progress(agent.agent_id, tid, prog, msg)
            )

            logger.info(f"エージェント {agent.agent_id} を登録しました")
            return True

        except Exception as e:
            logger.error(f"エージェント登録中にエラー: {e}")
            return False

    async def register_openhands(
        self, endpoint: str = "http://localhost:3000", config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """OpenHandsエージェントを登録（便利メソッド）

        Args:
            endpoint: OpenHandsのエンドポイント
            config: 追加の設定

        Returns:
            bool: 登録が成功した場合True
        """
        agent_config = {"endpoint": endpoint}
        if config:
            agent_config.update(config)

        agent = OpenHandsAgent(endpoint=endpoint)
        return await self.register_agent(agent, agent_config)

    async def submit_task(self, task: AgentTask) -> UUID:
        """タスクを送信

        Args:
            task: 実行するタスク

        Returns:
            UUID: タスクID
        """
        await self._task_queue.put(task)
        logger.info(f"タスク {task.id} をキューに追加しました")
        return task.id

    async def execute_task_immediately(
        self, task: AgentTask, agent_id: Optional[str] = None
    ) -> AgentResult:
        """タスクを即座に実行（キューをバイパス）

        Args:
            task: 実行するタスク
            agent_id: 使用するエージェントのID（省略時は自動選択）

        Returns:
            AgentResult: 実行結果
        """
        # エージェントを選択
        if agent_id:
            agent = self._agents.get(agent_id)
            if not agent:
                raise ValueError(f"エージェント {agent_id} が見つかりません")
        else:
            agent = self._select_agent_for_task(task)
            if not agent:
                raise ValueError("タスクを実行できるエージェントがありません")

        # タスクを実行
        self._running_tasks[task.id] = agent.agent_id

        try:
            result = await agent.execute_task(task)

            # 完了コールバックを呼び出し
            for callback in self._completion_callbacks:
                try:
                    await callback(task.id, result)
                except Exception as e:
                    logger.error(f"完了コールバック実行中にエラー: {e}")

            return result

        finally:
            self._running_tasks.pop(task.id, None)

    async def cancel_task(self, task_id: UUID) -> bool:
        """タスクをキャンセル

        Args:
            task_id: キャンセルするタスクのID

        Returns:
            bool: キャンセルが成功した場合True
        """
        agent_id = self._running_tasks.get(task_id)
        if not agent_id:
            return False

        agent = self._agents.get(agent_id)
        if not agent:
            return False

        return await agent.cancel_task(task_id)

    async def get_task_status(self, task_id: UUID) -> Optional[TaskStatus]:
        """タスクの状態を取得"""
        agent_id = self._running_tasks.get(task_id)
        if not agent_id:
            return None

        agent = self._agents.get(agent_id)
        if not agent:
            return None

        return await agent.get_task_status(task_id)

    async def get_task_progress(self, task_id: UUID) -> Optional[float]:
        """タスクの進捗を取得"""
        agent_id = self._running_tasks.get(task_id)
        if not agent_id:
            return None

        agent = self._agents.get(agent_id)
        if not agent:
            return None

        return await agent.get_task_progress(task_id)

    def resolve_intervention(self, agent_id: str, intervention_id: UUID, response: Any) -> bool:
        """ユーザー介入を解決

        Args:
            agent_id: エージェントID
            intervention_id: 介入ID
            response: ユーザーの応答

        Returns:
            bool: 解決が成功した場合True
        """
        agent = self._agents.get(agent_id)
        if not agent:
            return False

        if hasattr(agent, "resolve_intervention"):
            agent.resolve_intervention(intervention_id, response)
            return True

        return False

    def get_agents(self) -> Dict[str, Dict[str, Any]]:
        """登録されているエージェントの情報を取得"""
        return {agent_id: agent.get_agent_info() for agent_id, agent in self._agents.items()}

    def get_capabilities(self) -> Dict[str, List[str]]:
        """能力とそれをサポートするエージェントのマッピングを取得"""
        return {
            capability.value: list(agent_ids)
            for capability, agent_ids in self._capability_map.items()
        }

    def get_running_tasks(self) -> Dict[str, str]:
        """実行中のタスクを取得（task_id -> agent_id）"""
        return self._running_tasks.copy()

    def register_intervention_callback(
        self, callback: Callable[[UserIntervention, str], None]
    ) -> None:
        """ユーザー介入コールバックを登録"""
        if callback not in self._intervention_callbacks:
            self._intervention_callbacks.append(callback)

    def unregister_intervention_callback(
        self, callback: Callable[[UserIntervention, str], None]
    ) -> None:
        """ユーザー介入コールバックを解除"""
        if callback in self._intervention_callbacks:
            self._intervention_callbacks.remove(callback)

    def register_progress_callback(self, callback: Callable[[UUID, float, str, str], None]) -> None:
        """進捗通知コールバックを登録"""
        if callback not in self._progress_callbacks:
            self._progress_callbacks.append(callback)

    def unregister_progress_callback(
        self, callback: Callable[[UUID, float, str, str], None]
    ) -> None:
        """進捗通知コールバックを解除"""
        if callback in self._progress_callbacks:
            self._progress_callbacks.remove(callback)

    def register_completion_callback(self, callback: Callable[[UUID, AgentResult], None]) -> None:
        """タスク完了コールバックを登録"""
        if callback not in self._completion_callbacks:
            self._completion_callbacks.append(callback)

    def unregister_completion_callback(self, callback: Callable[[UUID, AgentResult], None]) -> None:
        """タスク完了コールバックを解除"""
        if callback in self._completion_callbacks:
            self._completion_callbacks.remove(callback)

    async def _task_worker(self) -> None:
        """タスクキューを処理するワーカー"""
        while self._is_running:
            try:
                # タスクを取得（タイムアウト付き）
                task = await asyncio.wait_for(self._task_queue.get(), timeout=1.0)

                # エージェントを選択
                agent = self._select_agent_for_task(task)
                if not agent:
                    logger.error(f"タスク {task.id} を実行できるエージェントがありません")
                    continue

                # タスクを実行（非同期）
                asyncio.create_task(self._execute_task_async(agent, task))

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"タスクワーカーでエラー: {e}")

    async def _execute_task_async(self, agent: AgentInterface, task: AgentTask) -> None:
        """タスクを非同期で実行"""
        self._running_tasks[task.id] = agent.agent_id

        try:
            result = await agent.execute_task(task)

            # 完了コールバックを呼び出し
            for callback in self._completion_callbacks:
                try:
                    await callback(task.id, result)
                except Exception as e:
                    logger.error(f"完了コールバック実行中にエラー: {e}")

        except Exception as e:
            logger.error(f"タスク {task.id} の実行中にエラー: {e}")
        finally:
            self._running_tasks.pop(task.id, None)

    def _select_agent_for_task(self, task: AgentTask) -> Optional[AgentInterface]:
        """タスクに適したエージェントを選択"""
        # 必要な能力をすべてサポートするエージェントを探す
        candidate_agents = None

        for capability in task.capabilities_required:
            agents_with_capability = self._capability_map.get(capability, set())
            if candidate_agents is None:
                candidate_agents = agents_with_capability.copy()
            else:
                candidate_agents &= agents_with_capability

        if not candidate_agents:
            return None

        # 最も負荷の低いエージェントを選択
        min_load = float("inf")
        selected_agent = None

        for agent_id in candidate_agents:
            agent = self._agents.get(agent_id)
            if not agent:
                continue

            # 実行中のタスク数を負荷として使用
            load = sum(1 for tid, aid in self._running_tasks.items() if aid == agent_id)

            if load < min_load:
                min_load = load
                selected_agent = agent

        return selected_agent

    async def _handle_agent_intervention(
        self, agent_id: str, intervention: UserIntervention
    ) -> None:
        """エージェントからの介入要求を処理"""
        for callback in self._intervention_callbacks:
            try:
                await callback(intervention, agent_id)
            except Exception as e:
                logger.error(f"介入コールバック実行中にエラー: {e}")

    async def _handle_agent_progress(
        self, agent_id: str, task_id: UUID, progress: float, message: str
    ) -> None:
        """エージェントからの進捗更新を処理"""
        for callback in self._progress_callbacks:
            try:
                await callback(task_id, progress, message, agent_id)
            except Exception as e:
                logger.error(f"進捗コールバック実行中にエラー: {e}")

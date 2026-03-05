"""LangChainエージェント実装

LangChainの機能を使用して会話メモリ、コンテキスト管理を行い、
必要に応じてOpenHandsエージェントにタスクを委譲します。
"""

import logging
import os
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from ...common.agent_protocol import (
    AgentCapability,
    AgentStatus,
    InterventionData,
    ProgressData,
    TaskData,
)
from ...langchain.containers import LangChainContainer
from ...langchain.memory.conversation_memory import ConversationMemoryManager
from ...langchain.models.conversation import ConversationType, MessageRole
from .base import AgentInterface
from .manager import AgentManager

logger = logging.getLogger(__name__)


class LangChainTaskType(str, Enum):
    """LangChainタスクタイプ"""

    ANALYZE = "analyze"
    SUMMARIZE = "summarize"
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    DOCUMENTATION = "documentation"
    TESTING = "testing"
    DEBUGGING = "debugging"
    REFACTORING = "refactoring"


class LangChainAgent(AgentInterface):
    """LangChainエージェント

    メモリ管理、コンテキスト保持、会話履歴管理を提供し、
    必要に応じてOpenHandsエージェントにタスクを委譲します。
    """

    def __init__(
        self,
        agent_id: str,
        agent_manager: Optional[AgentManager] = None,
        openhands_url: Optional[str] = None,
    ):
        """初期化

        Args:
            agent_id: エージェントID
            agent_manager: エージェントマネージャー（OpenHands連携用）
            openhands_url: OpenHandsサーバーURL
        """
        super().__init__(agent_id)
        self._status = AgentStatus.IDLE
        self._current_task: Optional[TaskData] = None
        self._container: Optional[LangChainContainer] = None
        self._conversation_memory: Optional[ConversationMemoryManager] = None
        self._agent_manager = agent_manager
        self._openhands_url = openhands_url or os.getenv("OPENHANDS_URL", "http://localhost:3000")
        self._openhands_agent_id: Optional[str] = None

        # コールバック
        self._progress_callback: Optional[Callable[[ProgressData], None]] = None
        self._intervention_callback: Optional[Callable[[InterventionData], Any]] = None

        # 実行統計
        self._task_history: List[Dict[str, Any]] = []

    async def initialize(self) -> bool:
        """エージェントを初期化"""
        try:
            logger.info(f"LangChainエージェント {self.agent_id} を初期化中...")

            # DIコンテナの初期化
            self._container = LangChainContainer()
            self._conversation_memory = self._container.conversation_memory_manager()

            # 階層化メモリマネージャーの初期化
            hierarchical_memory = self._container.hierarchical_memory_manager()
            await hierarchical_memory.initialize()

            self._status = AgentStatus.READY
            logger.info(f"LangChainエージェント {self.agent_id} の初期化が完了しました")
            return True

        except Exception as e:
            logger.error(f"LangChainエージェントの初期化に失敗しました: {e}")
            self._status = AgentStatus.ERROR
            return False

    async def shutdown(self) -> None:
        """エージェントをシャットダウン"""
        logger.info(f"LangChainエージェント {self.agent_id} をシャットダウン中...")

        # OpenHandsエージェントがある場合は停止
        if self._openhands_agent_id and self._agent_manager:
            await self._agent_manager.stop_agent(self._openhands_agent_id)

        # リソースのクリーンアップ
        if self._container:
            # コンテナのクリーンアップ処理
            pass

        self._status = AgentStatus.IDLE
        logger.info(f"LangChainエージェント {self.agent_id} のシャットダウンが完了しました")

    def get_capabilities(self) -> List[AgentCapability]:
        """エージェントの能力を取得"""
        capabilities = [
            AgentCapability.ANALYSIS,
            AgentCapability.MEMORY_MANAGEMENT,
            AgentCapability.CONTEXT_RETENTION,
        ]

        # OpenHandsが利用可能な場合は追加の能力
        if self._agent_manager:
            capabilities.extend(
                [
                    AgentCapability.CODE_GENERATION,
                    AgentCapability.CODE_EDITING,
                    AgentCapability.CODE_REVIEW,
                    AgentCapability.TESTING,
                    AgentCapability.DEBUGGING,
                    AgentCapability.DOCUMENTATION,
                ]
            )

        return capabilities

    def get_status(self) -> AgentStatus:
        """現在のステータスを取得"""
        return self._status

    async def execute_task(self, task: TaskData) -> Dict[str, Any]:
        """タスクを実行

        Args:
            task: 実行するタスク

        Returns:
            Dict[str, Any]: 実行結果
        """
        self._current_task = task
        self._status = AgentStatus.BUSY

        try:
            # 会話履歴に記録
            await self._store_conversation(
                f"タスク開始: {task.task_type} - {task.description}",
                ConversationType.SYSTEM_MESSAGE,
            )

            # タスクタイプに応じて処理を分岐
            result = await self._process_task(task)

            # 成功を記録
            self._task_history.append(
                {
                    "task_id": task.task_id,
                    "task_type": task.task_type,
                    "status": "completed",
                    "timestamp": datetime.now().isoformat(),
                }
            )

            # 会話履歴に結果を記録
            await self._store_conversation(
                f"タスク完了: {task.task_type}", ConversationType.SYSTEM_MESSAGE
            )

            self._status = AgentStatus.READY
            return result

        except Exception as e:
            logger.error(f"タスク実行中にエラーが発生しました: {e}")

            # エラーを記録
            self._task_history.append(
                {
                    "task_id": task.task_id,
                    "task_type": task.task_type,
                    "status": "error",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
            )

            self._status = AgentStatus.ERROR
            raise

        finally:
            self._current_task = None

    async def cancel_task(self) -> bool:
        """現在のタスクをキャンセル"""
        if not self._current_task:
            return False

        logger.info(f"タスク {self._current_task.task_id} をキャンセル中...")

        # OpenHandsエージェントが実行中の場合はキャンセル
        if self._openhands_agent_id and self._agent_manager:
            openhands_agent = self._agent_manager.get_agent(self._openhands_agent_id)
            if openhands_agent:
                await openhands_agent.cancel_task()

        self._current_task = None
        self._status = AgentStatus.READY
        return True

    def set_progress_callback(self, callback: Callable[[ProgressData], None]) -> None:
        """進捗通知コールバックを設定"""
        self._progress_callback = callback

    def set_intervention_callback(self, callback: Callable[[InterventionData], Any]) -> None:
        """ユーザー介入コールバックを設定"""
        self._intervention_callback = callback

    async def _process_task(self, task: TaskData) -> Dict[str, Any]:
        """タスクを処理

        Args:
            task: 処理するタスク

        Returns:
            Dict[str, Any]: 処理結果
        """
        task_type = LangChainTaskType(task.task_type)

        # メモリから関連情報を取得
        context = await self._get_relevant_context(task)

        # コード生成・編集系のタスクはOpenHandsに委譲
        if task_type in [
            LangChainTaskType.CODE_GENERATION,
            LangChainTaskType.CODE_REVIEW,
            LangChainTaskType.TESTING,
            LangChainTaskType.DEBUGGING,
            LangChainTaskType.REFACTORING,
        ]:
            return await self._delegate_to_openhands(task, context)

        # 分析・要約系のタスクは自身で処理
        if task_type == LangChainTaskType.ANALYZE:
            return await self._analyze_task(task, context)

        if task_type == LangChainTaskType.SUMMARIZE:
            return await self._summarize_task(task, context)

        if task_type == LangChainTaskType.DOCUMENTATION:
            return await self._create_documentation(task, context)

        raise ValueError(f"未対応のタスクタイプ: {task_type}")

    async def _delegate_to_openhands(
        self, task: TaskData, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """OpenHandsエージェントにタスクを委譲

        Args:
            task: 委譲するタスク
            context: タスクコンテキスト

        Returns:
            Dict[str, Any]: 実行結果
        """
        if not self._agent_manager:
            raise RuntimeError("エージェントマネージャーが設定されていません")

        # 進捗を通知
        await self._notify_progress(0.1, "OpenHandsエージェントを準備中...")

        # OpenHandsエージェントを取得または作成
        if not self._openhands_agent_id:
            # エージェントを作成
            from .openhands import OpenHandsAgent

            openhands_agent = OpenHandsAgent(
                agent_id=f"openhands_{uuid4().hex[:8]}", base_url=self._openhands_url
            )

            # マネージャーに登録
            self._agent_manager.register_agent(openhands_agent)
            self._openhands_agent_id = openhands_agent.agent_id

            # エージェントを開始
            await self._agent_manager.start_agent(self._openhands_agent_id)

        # コンテキストを含めたタスクデータを作成
        enhanced_task = TaskData(
            task_id=task.task_id,
            task_type=task.task_type,
            description=f"{task.description}\n\nコンテキスト:\n{self._format_context(context)}",
            parameters=task.parameters,
            priority=task.priority,
            dependencies=task.dependencies,
        )

        # 進捗を通知
        await self._notify_progress(0.3, "OpenHandsエージェントにタスクを委譲中...")

        # タスクを実行
        result = await self._agent_manager.execute_task(self._openhands_agent_id, enhanced_task)

        # 結果を会話履歴に保存
        await self._store_conversation(
            f"OpenHandsタスク完了: {task.task_type}", ConversationType.ASSISTANT_OUTPUT
        )

        # 進捗を通知
        await self._notify_progress(1.0, "タスクが完了しました")

        return result

    async def _analyze_task(self, task: TaskData, context: Dict[str, Any]) -> Dict[str, Any]:
        """分析タスクを実行"""
        await self._notify_progress(0.2, "コンテキストを分析中...")

        # ここで実際の分析ロジックを実装
        # 今回はデモとして簡単な実装
        analysis_result = {
            "summary": f"{task.description}の分析結果",
            "context_items": len(context.get("relevant_memories", [])),
            "recommendations": [
                "コードの構造を改善することを推奨",
                "テストカバレッジを向上させることを推奨",
            ],
        }

        await self._notify_progress(1.0, "分析が完了しました")
        return analysis_result

    async def _summarize_task(self, task: TaskData, context: Dict[str, Any]) -> Dict[str, Any]:
        """要約タスクを実行"""
        await self._notify_progress(0.2, "情報を収集中...")

        # ここで実際の要約ロジックを実装
        summary_result = {
            "summary": f"{task.description}の要約",
            "key_points": ["重要なポイント1", "重要なポイント2"],
            "context_used": len(context.get("relevant_memories", [])),
        }

        await self._notify_progress(1.0, "要約が完了しました")
        return summary_result

    async def _create_documentation(
        self, task: TaskData, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """ドキュメント作成タスクを実行"""
        await self._notify_progress(0.2, "ドキュメントを生成中...")

        # ここで実際のドキュメント生成ロジックを実装
        doc_result = {
            "documentation": f"# {task.description}\n\n## 概要\n\nドキュメントの内容...",
            "format": "markdown",
            "sections": ["概要", "使用方法", "API リファレンス"],
        }

        await self._notify_progress(1.0, "ドキュメント作成が完了しました")
        return doc_result

    async def _get_relevant_context(self, task: TaskData) -> Dict[str, Any]:
        """タスクに関連するコンテキストを取得

        Args:
            task: タスク情報

        Returns:
            Dict[str, Any]: 関連コンテキスト
        """
        if not self._conversation_memory:
            return {}

        # 会話履歴から関連情報を検索
        try:
            recent_conversations = await self._conversation_memory.get_recent_conversations(
                session_id=self.agent_id, limit=10
            )

            # キーワードベースで関連メモリを検索
            keywords = task.description.split()[:5]  # 最初の5単語をキーワードとして使用
            relevant_memories = await self._conversation_memory.search_conversations(
                session_id=self.agent_id, query=" ".join(keywords), limit=5
            )

            return {
                "recent_conversations": recent_conversations,
                "relevant_memories": relevant_memories,
                "task_history": self._task_history[-5:],  # 最近の5タスク
            }

        except Exception as e:
            logger.warning(f"コンテキスト取得中にエラーが発生しました: {e}")
            return {}

    async def _store_conversation(self, content: str, conversation_type: ConversationType) -> None:
        """会話を保存"""
        if not self._conversation_memory:
            return

        try:
            await self._conversation_memory.store_conversation(
                session_id=self.agent_id,
                content=content,
                conversation_type=conversation_type,
                role=MessageRole.ASSISTANT
                if conversation_type == ConversationType.ASSISTANT_OUTPUT
                else MessageRole.SYSTEM,
                metadata={
                    "agent_type": "langchain",
                    "task_id": self._current_task.task_id if self._current_task else None,
                },
            )
        except Exception as e:
            logger.warning(f"会話の保存中にエラーが発生しました: {e}")

    async def _notify_progress(self, percentage: float, message: str) -> None:
        """進捗を通知"""
        if self._progress_callback and self._current_task:
            progress_data = ProgressData(
                task_id=self._current_task.task_id,
                percentage=percentage,
                message=message,
                details={},
            )
            self._progress_callback(progress_data)

    def _format_context(self, context: Dict[str, Any]) -> str:
        """コンテキストをフォーマット"""
        lines = []

        if "recent_conversations" in context:
            lines.append("最近の会話:")
            for conv in context["recent_conversations"][-3:]:  # 最新3件
                lines.append(f"- {conv.get('content', '')}")

        if "relevant_memories" in context:
            lines.append("\n関連するメモリ:")
            for mem in context["relevant_memories"][:3]:  # 上位3件
                lines.append(f"- {mem.get('content', '')}")

        if "task_history" in context:
            lines.append("\n最近のタスク:")
            for task in context["task_history"]:
                lines.append(f"- {task.get('task_type', '')}: {task.get('status', '')}")

        return "\n".join(lines)

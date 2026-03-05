"""
LangChainエージェント実装

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
    """
    LangChainエージェント

    メモリ管理、コンテキスト保持、会話履歴管理を提供し、
    必要に応じてOpenHandsエージェントにタスクを委譲します。
    """

    def __init__(
        self,
        agent_id: str,
        agent_manager: Optional[AgentManager] = None,
        openhands_url: Optional[str] = None,
    ):
        """
        初期化

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
        """
        タスクを実行

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
        """
        タスクを処理

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
        """
        OpenHandsエージェントにタスクを委譲

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
        """
        分析タスクを実行

        コンテキストとメモリ情報を活用して、タスク内容を多角的に分析します。
        コマンド解析の場合はCommandAnalyzerAgentと連携します。
        """
        await self._notify_progress(0.1, "コンテキストを収集中...")

        description = task.description
        parameters = task.parameters or {}

        # コンテキスト情報を構築
        relevant_memories = context.get("relevant_memories", [])
        recent_conversations = context.get("recent_conversations", [])
        task_history_items = context.get("task_history", [])

        await self._notify_progress(0.3, "メモリから関連情報を取得中...")

        # 分析対象に応じた処理
        analysis_type = parameters.get("analysis_type", "general")
        result: Dict[str, Any] = {}

        if analysis_type == "command" and "command" in parameters:
            # コマンド解析：CommandAnalyzerAgentと同様のパターン解析
            result = await self._analyze_command_with_context(
                parameters["command"], context
            )

        elif analysis_type == "code" and "code" in parameters:
            # コード分析
            result = self._analyze_code(parameters["code"], context)

        elif analysis_type == "workflow":
            # ワークフロー分析
            result = self._analyze_workflow(description, task_history_items)

        else:
            # 汎用分析
            result = {
                "type": "general_analysis",
                "description": description,
                "context_items_used": len(relevant_memories),
                "related_conversations": len(recent_conversations),
                "insights": [],
                "recommendations": [],
            }

            # コンテキストから洞察を生成
            if relevant_memories:
                result["insights"].append(
                    f"メモリから{len(relevant_memories)}件の関連情報を発見"
                )
                for mem in relevant_memories[:3]:
                    content = mem.get("content", "")
                    if content:
                        result["insights"].append(f"関連: {content[:100]}")

            if task_history_items:
                # 過去のタスク結果から推奨事項を生成
                failed_tasks = [t for t in task_history_items if t.get("status") == "error"]
                if failed_tasks:
                    result["recommendations"].append(
                        f"直近で{len(failed_tasks)}件のタスクが失敗しています。関連する問題がないか確認してください"
                    )

                completed_types = set(t.get("task_type", "") for t in task_history_items if t.get("status") == "completed")
                if completed_types:
                    result["recommendations"].append(
                        f"完了済みタスクタイプ: {', '.join(completed_types)}"
                    )

        result["summary"] = f"{description}の分析完了（コンテキスト{len(relevant_memories)}件使用）"

        # 結果をメモリに保存
        await self._store_conversation(
            f"分析結果: {result.get('summary', '')}",
            ConversationType.ASSISTANT_OUTPUT,
        )

        await self._notify_progress(1.0, "分析が完了しました")
        return result

    async def _analyze_command_with_context(
        self, command: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        コンテキストを考慮したコマンド解析

        メモリ内の過去のコマンド履歴と比較し、
        コンテキスト認識型のリスク判定を行います。
        """
        import re

        # 基本的な危険パターン（POCのCommandAnalysisToolから統合）
        danger_patterns = {
            "root_delete": re.compile(r"rm\s+.*(-rf|-fr).*\s+/\s*($|\s)"),
            "format_disk": re.compile(r"(mkfs|format|fdisk)"),
            "dd_system": re.compile(r"dd.*of=/dev/(sda|hda|nvme0n1)"),
            "fork_bomb": re.compile(
                r":\(\)\{:\|:&\};:|:\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"
            ),
            "system_files": re.compile(r"(rm|dd|>).*(etc|bin|boot|sys)"),
        }

        issues = []
        risk_level = "safe"

        for pattern_name, pattern in danger_patterns.items():
            if pattern.search(command):
                if pattern_name == "fork_bomb":
                    issues.append("フォーク爆弾を検出しました")
                    risk_level = "critical"
                elif pattern_name == "root_delete":
                    issues.append("ルートディレクトリの削除は非常に危険です")
                    risk_level = "critical"
                elif pattern_name == "dd_system":
                    issues.append("システムディスクへの直接書き込みは危険です")
                    risk_level = "critical"
                elif pattern_name == "format_disk":
                    issues.append("ディスクのフォーマット操作を検出しました")
                    risk_level = "dangerous"
                elif pattern_name == "system_files":
                    issues.append("システムファイルへの破壊的操作を検出しました")
                    if risk_level not in ("critical",):
                        risk_level = "dangerous"

        # コンテキストベースの分析
        recent_conversations = context.get("recent_conversations", [])
        context_insights = []
        if recent_conversations:
            for conv in recent_conversations[-3:]:
                content = conv.get("content", "")
                if "cd" in content and "rm" in command:
                    context_insights.append(
                        "直前にディレクトリ変更があります。現在位置を確認してください"
                    )

        return {
            "type": "command_analysis",
            "command": command,
            "risk_level": risk_level,
            "issues": issues,
            "context_insights": context_insights,
            "requires_confirmation": risk_level in ("dangerous", "critical"),
        }

    def _analyze_code(self, code: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """コード分析"""
        lines = code.strip().split("\n")
        return {
            "type": "code_analysis",
            "line_count": len(lines),
            "has_imports": any(line.strip().startswith(("import ", "from ")) for line in lines),
            "has_classes": any("class " in line for line in lines),
            "has_functions": any("def " in line for line in lines),
            "context_items_used": len(context.get("relevant_memories", [])),
        }

    def _analyze_workflow(
        self, description: str, task_history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """ワークフロー分析"""
        completed = [t for t in task_history if t.get("status") == "completed"]
        failed = [t for t in task_history if t.get("status") == "error"]

        return {
            "type": "workflow_analysis",
            "description": description,
            "total_tasks": len(task_history),
            "completed_tasks": len(completed),
            "failed_tasks": len(failed),
            "success_rate": len(completed) / len(task_history) if task_history else 0,
            "recommendations": [
                "失敗タスクのリトライを検討してください" if failed else "全タスクが正常に完了しています"
            ],
        }

    async def _summarize_task(self, task: TaskData, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        要約タスクを実行

        メモリから関連情報を収集し、コンテキストを考慮した要約を生成します。
        """
        await self._notify_progress(0.1, "情報を収集中...")

        relevant_memories = context.get("relevant_memories", [])
        recent_conversations = context.get("recent_conversations", [])

        # 会話履歴からキーポイントを抽出
        key_points = []
        for conv in recent_conversations:
            content = conv.get("content", "")
            if len(content) > 10:
                key_points.append(content[:200])

        await self._notify_progress(0.5, "要約を生成中...")

        # メモリから追加の情報を取得
        memory_insights = []
        for mem in relevant_memories[:5]:
            content = mem.get("content", "")
            if content:
                memory_insights.append(content[:150])

        summary_result = {
            "summary": f"{task.description}の要約（{len(recent_conversations)}件の会話から生成）",
            "key_points": key_points[:10],
            "memory_insights": memory_insights,
            "context_used": len(relevant_memories),
            "conversation_count": len(recent_conversations),
        }

        # 結果をメモリに保存
        await self._store_conversation(
            f"要約生成完了: {summary_result['summary']}",
            ConversationType.ASSISTANT_OUTPUT,
        )

        await self._notify_progress(1.0, "要約が完了しました")
        return summary_result

    async def _create_documentation(
        self, task: TaskData, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        ドキュメント作成タスクを実行

        メモリとコンテキストから情報を収集し、構造化されたドキュメントを生成します。
        """
        await self._notify_progress(0.1, "ドキュメント構造を計画中...")

        description = task.description
        parameters = task.parameters or {}
        doc_format = parameters.get("format", "markdown")

        relevant_memories = context.get("relevant_memories", [])
        task_history = context.get("task_history", [])

        await self._notify_progress(0.3, "コンテンツを収集中...")

        # ドキュメントのセクションを構築
        sections = ["概要"]
        content_parts = [f"# {description}\n"]

        # 概要セクション
        content_parts.append("## 概要\n")
        if relevant_memories:
            content_parts.append("関連する情報に基づいて作成されたドキュメントです。\n")
        else:
            content_parts.append("新規作成されたドキュメントです。\n")

        # タスク履歴がある場合は実行ログセクションを追加
        if task_history:
            sections.append("実行ログ")
            content_parts.append("\n## 実行ログ\n")
            for t in task_history[-5:]:
                status = t.get("status", "unknown")
                task_type = t.get("task_type", "unknown")
                content_parts.append(f"- **{task_type}**: {status}\n")

        # メモリからの関連情報セクション
        if relevant_memories:
            sections.append("関連情報")
            content_parts.append("\n## 関連情報\n")
            for mem in relevant_memories[:5]:
                content = mem.get("content", "")
                if content:
                    content_parts.append(f"- {content[:200]}\n")

        # API リファレンスセクション（パラメータで指定された場合）
        if parameters.get("include_api_reference"):
            sections.append("API リファレンス")
            content_parts.append("\n## API リファレンス\n")
            content_parts.append("（API仕様に基づいて自動生成）\n")

        await self._notify_progress(0.7, "ドキュメントを組み立て中...")

        doc_content = "\n".join(content_parts)

        doc_result = {
            "documentation": doc_content,
            "format": doc_format,
            "sections": sections,
            "context_used": len(relevant_memories),
            "word_count": len(doc_content.split()),
        }

        # 結果をメモリに保存
        await self._store_conversation(
            f"ドキュメント作成完了: {description} ({len(sections)}セクション)",
            ConversationType.ASSISTANT_OUTPUT,
        )

        await self._notify_progress(1.0, "ドキュメント作成が完了しました")
        return doc_result

    async def _get_relevant_context(self, task: TaskData) -> Dict[str, Any]:
        """
        タスクに関連するコンテキストを取得

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

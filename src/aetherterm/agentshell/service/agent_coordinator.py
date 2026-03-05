"""
エージェントコーディネーター

複数の子エージェント間の依頼調整、競合解決、
タスク分配を行う高度な調整機能を提供します。
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID, uuid4

from ...common.agent_protocol import AgentMessage, MessageBuilder, MessageType
from ..agents.base import AgentCapability, AgentTask, TaskStatus

logger = logging.getLogger(__name__)


class ConflictType(str, Enum):
    """競合タイプ"""
    FILE_CONFLICT = "file_conflict"          # 同じファイルを編集
    RESOURCE_CONFLICT = "resource_conflict"  # 同じリソースにアクセス
    DEPENDENCY_CONFLICT = "dependency_conflict"  # 依存関係の競合
    LOGICAL_CONFLICT = "logical_conflict"    # ロジックレベルの競合
    TIMING_CONFLICT = "timing_conflict"      # タイミングの競合


class CoordinationStrategy(str, Enum):
    """調整戦略"""
    SEQUENTIAL = "sequential"      # 順次実行
    PARALLEL = "parallel"          # 並列実行
    COLLABORATIVE = "collaborative"  # 協調実行
    COMPETITIVE = "competitive"    # 競争実行（最初に完了したものを採用）


@dataclass
class TaskDependency:
    """タスク依存関係"""
    task_id: UUID
    depends_on: List[UUID] = field(default_factory=list)
    blocks: List[UUID] = field(default_factory=list)
    shared_resources: List[str] = field(default_factory=list)
    
    
@dataclass
class ConflictResolution:
    """競合解決結果"""
    conflict_id: UUID = field(default_factory=uuid4)
    conflict_type: ConflictType = ConflictType.LOGICAL_CONFLICT
    affected_agents: List[str] = field(default_factory=list)
    resolution: str = ""
    adjustments: Dict[str, Any] = field(default_factory=dict)
    

@dataclass
class InterAgentRequest:
    """エージェント間リクエスト"""
    request_id: UUID = field(default_factory=uuid4)
    from_agent: str = ""
    to_agent: str = ""
    request_type: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: int = 5
    deadline: Optional[datetime] = None
    

class AgentCoordinator:
    """
    エージェントコーディネーター

    複数のエージェント間の作業を調整し、
    競合を解決してスムーズな協調作業を実現します。
    セキュリティ意識のある判定と過去の決定からの学習機能を備えます。
    """

    # セキュリティ：危険なキーワード（POCから統合）
    DANGEROUS_KEYWORDS = frozenset([
        "delete", "drop", "remove", "production", "prod",
        "truncate", "destroy", "format", "purge",
    ])

    # セキュリティ：保護対象環境パターン
    PROTECTED_ENVIRONMENTS = frozenset([
        "production", "prod", "main", "master", "live",
    ])

    def __init__(self):
        self._active_agents: Dict[str, Dict[str, Any]] = {}
        self._task_dependencies: Dict[UUID, TaskDependency] = {}
        self._resource_locks: Dict[str, str] = {}  # resource -> agent_id
        self._pending_requests: List[InterAgentRequest] = []
        self._conflict_history: List[ConflictResolution] = []
        self._coordination_rules: List[Dict[str, Any]] = []

        # 学習：過去の解決パターンの成功率（POCから統合）
        self._resolution_success_rates: Dict[str, Dict[str, float]] = {}
        # 学習：エージェントタイプ別の優先度マップ
        self._agent_type_priorities: Dict[str, int] = {
            "security": 100,
            "monitoring": 80,
            "analysis": 60,
            "code_generation": 50,
            "documentation": 30,
        }
        
    async def register_agent_task(
        self,
        agent_id: str,
        task: AgentTask,
        resources: List[str],
        dependencies: Optional[List[UUID]] = None
    ) -> None:
        """
        エージェントのタスクを登録
        
        Args:
            agent_id: エージェントID
            task: タスク
            resources: 使用するリソース（ファイル、API等）
            dependencies: 依存するタスクID
        """
        # エージェント情報を更新
        if agent_id not in self._active_agents:
            self._active_agents[agent_id] = {
                "tasks": {},
                "resources": set(),
                "capabilities": []
            }
        
        self._active_agents[agent_id]["tasks"][task.id] = task
        self._active_agents[agent_id]["resources"].update(resources)
        
        # 依存関係を登録
        self._task_dependencies[task.id] = TaskDependency(
            task_id=task.id,
            depends_on=dependencies or [],
            shared_resources=resources
        )
        
        # 競合チェック
        conflicts = await self._detect_conflicts(agent_id, task, resources)
        if conflicts:
            await self._resolve_conflicts(conflicts)
    
    async def request_inter_agent_collaboration(
        self,
        from_agent: str,
        to_agent: str,
        request_type: str,
        payload: Dict[str, Any],
        priority: int = 5
    ) -> UUID:
        """
        エージェント間の協力を要求
        
        Args:
            from_agent: 要求元エージェント
            to_agent: 要求先エージェント
            request_type: 要求タイプ
            payload: 要求内容
            priority: 優先度
            
        Returns:
            UUID: リクエストID
        """
        request = InterAgentRequest(
            from_agent=from_agent,
            to_agent=to_agent,
            request_type=request_type,
            payload=payload,
            priority=priority
        )
        
        # 調整ルールをチェック
        if await self._should_allow_request(request):
            self._pending_requests.append(request)
            await self._process_inter_agent_request(request)
        else:
            logger.warning(f"エージェント間リクエストが拒否されました: {request_type}")
            
        return request.request_id
    
    async def coordinate_parallel_work(
        self,
        agents: List[str],
        shared_goal: str,
        strategy: CoordinationStrategy = CoordinationStrategy.COLLABORATIVE
    ) -> Dict[str, AgentTask]:
        """
        並列作業を調整
        
        Args:
            agents: 参加エージェントのリスト
            shared_goal: 共通の目標
            strategy: 調整戦略
            
        Returns:
            Dict[str, AgentTask]: エージェント別のタスク割り当て
        """
        logger.info(f"並列作業を調整: {shared_goal} (戦略: {strategy})")
        
        # 作業を分析して分割
        subtasks = await self._analyze_and_split_work(shared_goal, len(agents))
        
        # エージェントの能力を考慮してタスクを割り当て
        assignments = {}
        
        for i, agent_id in enumerate(agents):
            agent_info = self._active_agents.get(agent_id, {})
            capabilities = agent_info.get("capabilities", [])
            
            # 最適なタスクを選択
            best_task = self._select_best_task_for_agent(
                subtasks, capabilities, assignments
            )
            
            if best_task:
                assignments[agent_id] = best_task
                subtasks.remove(best_task)
        
        # 依存関係を設定
        if strategy == CoordinationStrategy.SEQUENTIAL:
            await self._setup_sequential_dependencies(assignments)
        elif strategy == CoordinationStrategy.COLLABORATIVE:
            await self._setup_collaborative_dependencies(assignments)
            
        return assignments
    
    async def detect_and_resolve_conflicts(
        self,
        agent1: str,
        agent2: str,
        context: Dict[str, Any]
    ) -> ConflictResolution:
        """
        エージェント間の競合を検出して解決
        
        Args:
            agent1: エージェント1
            agent2: エージェント2
            context: 競合のコンテキスト
            
        Returns:
            ConflictResolution: 解決結果
        """
        # 競合タイプを特定
        conflict_type = await self._identify_conflict_type(agent1, agent2, context)
        
        # 解決戦略を決定
        resolution_strategy = await self._determine_resolution_strategy(
            conflict_type, agent1, agent2, context
        )
        
        # 解決を実行
        resolution = ConflictResolution(
            conflict_type=conflict_type,
            affected_agents=[agent1, agent2],
            resolution=resolution_strategy
        )
        
        if conflict_type == ConflictType.FILE_CONFLICT:
            # ファイル競合の解決
            resolution.adjustments = await self._resolve_file_conflict(
                agent1, agent2, context
            )
        elif conflict_type == ConflictType.RESOURCE_CONFLICT:
            # リソース競合の解決
            resolution.adjustments = await self._resolve_resource_conflict(
                agent1, agent2, context
            )
        elif conflict_type == ConflictType.LOGICAL_CONFLICT:
            # ロジック競合の解決
            resolution.adjustments = await self._resolve_logical_conflict(
                agent1, agent2, context
            )
            
        self._conflict_history.append(resolution)
        return resolution
    
    async def _detect_conflicts(
        self,
        agent_id: str,
        task: AgentTask,
        resources: List[str]
    ) -> List[Dict[str, Any]]:
        """競合を検出"""
        conflicts = []
        
        # リソース競合をチェック
        for resource in resources:
            if resource in self._resource_locks:
                owner = self._resource_locks[resource]
                if owner != agent_id:
                    conflicts.append({
                        "type": ConflictType.RESOURCE_CONFLICT,
                        "agents": [agent_id, owner],
                        "resource": resource
                    })
        
        # ファイル編集の競合をチェック
        for other_agent, info in self._active_agents.items():
            if other_agent == agent_id:
                continue
                
            shared_resources = set(resources) & info["resources"]
            if shared_resources:
                # ファイルパスの競合を詳細にチェック
                for resource in shared_resources:
                    if resource.endswith(('.py', '.js', '.ts', '.java')):
                        conflicts.append({
                            "type": ConflictType.FILE_CONFLICT,
                            "agents": [agent_id, other_agent],
                            "file": resource
                        })
        
        return conflicts
    
    async def _resolve_conflicts(
        self,
        conflicts: List[Dict[str, Any]]
    ) -> None:
        """競合を解決"""
        for conflict in conflicts:
            conflict_type = conflict["type"]
            agents = conflict["agents"]
            
            logger.info(f"競合を検出: {conflict_type} - エージェント: {agents}")
            
            # 解決戦略を適用
            resolution = await self.detect_and_resolve_conflicts(
                agents[0], agents[1], conflict
            )
            
            # エージェントに調整を通知
            for agent_id in agents:
                await self._notify_agent_adjustment(
                    agent_id, resolution
                )
    
    async def _resolve_file_conflict(
        self,
        agent1: str,
        agent2: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """ファイル編集の競合を解決"""
        file_path = context.get("file", "")
        
        # 戦略1: セクション分割
        # ファイルの異なる部分を編集するように調整
        adjustments = {
            agent1: {
                "action": "edit_section",
                "section": "top_half",
                "wait_for": None
            },
            agent2: {
                "action": "edit_section", 
                "section": "bottom_half",
                "wait_for": None
            }
        }
        
        # 戦略2: 順次編集
        # より重要なタスクを先に実行
        priority1 = self._get_agent_priority(agent1)
        priority2 = self._get_agent_priority(agent2)
        
        if priority1 > priority2:
            adjustments[agent2]["wait_for"] = agent1
        else:
            adjustments[agent1]["wait_for"] = agent2
            
        return adjustments
    
    async def _resolve_resource_conflict(
        self,
        agent1: str,
        agent2: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """リソース競合を解決"""
        resource = context.get("resource", "")
        
        # タイムスライシング戦略
        return {
            agent1: {
                "action": "use_resource",
                "time_slot": "0-30min",
                "resource": resource
            },
            agent2: {
                "action": "use_resource",
                "time_slot": "30-60min",
                "resource": resource
            }
        }
    
    async def _resolve_logical_conflict(
        self,
        agent1: str,
        agent2: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """ロジック競合を解決"""
        # AIを使用して最適な解決策を決定
        return {
            "strategy": "merge",
            "primary_agent": agent1,
            "secondary_agent": agent2,
            "merge_points": ["interface", "implementation"]
        }
    
    async def _identify_conflict_type(
        self,
        agent1: str,
        agent2: str,
        context: Dict[str, Any]
    ) -> ConflictType:
        """競合タイプを特定"""
        if "file" in context:
            return ConflictType.FILE_CONFLICT
        elif "resource" in context:
            return ConflictType.RESOURCE_CONFLICT
        elif "dependency" in context:
            return ConflictType.DEPENDENCY_CONFLICT
        elif "timing" in context:
            return ConflictType.TIMING_CONFLICT
        else:
            return ConflictType.LOGICAL_CONFLICT
    
    async def _determine_resolution_strategy(
        self,
        conflict_type: ConflictType,
        agent1: str,
        agent2: str,
        context: Dict[str, Any]
    ) -> str:
        """解決戦略を決定"""
        strategies = {
            ConflictType.FILE_CONFLICT: "section_split",
            ConflictType.RESOURCE_CONFLICT: "time_sharing",
            ConflictType.DEPENDENCY_CONFLICT: "reorder",
            ConflictType.LOGICAL_CONFLICT: "merge",
            ConflictType.TIMING_CONFLICT: "reschedule"
        }
        
        return strategies.get(conflict_type, "negotiate")
    
    async def _analyze_and_split_work(
        self,
        goal: str,
        num_agents: int
    ) -> List[AgentTask]:
        """作業を分析して分割"""
        # 簡単な実装例
        subtasks = []
        
        # 目標に基づいてタスクを生成
        if "implement" in goal.lower():
            task_types = ["design", "implement", "test", "document"]
        else:
            task_types = ["analyze", "plan", "execute", "verify"]
        
        for i, task_type in enumerate(task_types[:num_agents]):
            subtasks.append(AgentTask(
                type=task_type,
                description=f"{goal} - {task_type}",
                priority=10 - i
            ))
            
        return subtasks
    
    def _select_best_task_for_agent(
        self,
        available_tasks: List[AgentTask],
        capabilities: List[AgentCapability],
        existing_assignments: Dict[str, AgentTask]
    ) -> Optional[AgentTask]:
        """エージェントに最適なタスクを選択"""
        if not available_tasks:
            return None
            
        # 能力に基づいてスコアリング
        best_task = None
        best_score = -1
        
        for task in available_tasks:
            score = 0
            
            # 必要な能力がある場合はスコアを上げる
            for required_cap in task.capabilities_required:
                if required_cap in capabilities:
                    score += 10
                    
            # タスクタイプとの適合性
            if task.type == "test" and AgentCapability.TESTING in capabilities:
                score += 5
            elif task.type == "implement" and AgentCapability.CODE_GENERATION in capabilities:
                score += 5
                
            if score > best_score:
                best_score = score
                best_task = task
                
        return best_task
    
    async def _setup_sequential_dependencies(
        self,
        assignments: Dict[str, AgentTask]
    ) -> None:
        """順次実行の依存関係を設定"""
        agents = list(assignments.keys())
        
        for i in range(len(agents) - 1):
            current_task = assignments[agents[i]]
            next_task = assignments[agents[i + 1]]
            
            if next_task.id in self._task_dependencies:
                self._task_dependencies[next_task.id].depends_on.append(current_task.id)
    
    async def _setup_collaborative_dependencies(
        self,
        assignments: Dict[str, AgentTask]
    ) -> None:
        """協調実行の依存関係を設定"""
        # 共有リソースに基づいて依存関係を設定
        for agent1, task1 in assignments.items():
            for agent2, task2 in assignments.items():
                if agent1 != agent2:
                    # 共有リソースがある場合は相互依存
                    shared = set(self._task_dependencies[task1.id].shared_resources) & \
                            set(self._task_dependencies[task2.id].shared_resources)
                    if shared:
                        self._task_dependencies[task1.id].blocks.append(task2.id)
    
    async def _should_allow_request(
        self,
        request: InterAgentRequest
    ) -> bool:
        """リクエストを許可すべきか判断"""
        # ルールベースのチェック
        for rule in self._coordination_rules:
            if rule["type"] == "block_request":
                if (rule["from_agent"] == request.from_agent and
                    rule["to_agent"] == request.to_agent and
                    rule["request_type"] == request.request_type):
                    return False
                    
        # リソースの可用性チェック
        if "resource" in request.payload:
            resource = request.payload["resource"]
            if resource in self._resource_locks:
                return False
                
        return True
    
    async def _process_inter_agent_request(
        self,
        request: InterAgentRequest
    ) -> None:
        """エージェント間リクエストを処理"""
        logger.info(f"エージェント間リクエストを処理: {request.request_type}")
        
        # リクエストタイプに応じた処理
        if request.request_type == "delegate_task":
            # タスク委譲
            await self._handle_task_delegation(request)
        elif request.request_type == "request_resource":
            # リソース要求
            await self._handle_resource_request(request)
        elif request.request_type == "sync_state":
            # 状態同期
            await self._handle_state_sync(request)
    
    async def _handle_task_delegation(
        self,
        request: InterAgentRequest
    ) -> None:
        """タスク委譲を処理"""
        task = request.payload.get("task")
        if task:
            # 受信エージェントにタスクを割り当て
            await self.register_agent_task(
                request.to_agent,
                task,
                request.payload.get("resources", [])
            )
    
    async def _handle_resource_request(
        self,
        request: InterAgentRequest
    ) -> None:
        """リソース要求を処理"""
        resource = request.payload.get("resource")
        if resource and resource not in self._resource_locks:
            self._resource_locks[resource] = request.from_agent
            logger.info(f"リソース {resource} を {request.from_agent} にロック")
    
    async def _handle_state_sync(
        self,
        request: InterAgentRequest
    ) -> None:
        """状態同期を処理"""
        state = request.payload.get("state", {})
        # エージェントの状態を更新
        if request.from_agent in self._active_agents:
            self._active_agents[request.from_agent].update(state)
    
    def _get_agent_priority(self, agent_id: str) -> int:
        """エージェントの優先度を取得"""
        # 実行中のタスクの優先度から決定
        agent_info = self._active_agents.get(agent_id, {})
        tasks = agent_info.get("tasks", {})
        
        if tasks:
            max_priority = max(task.priority for task in tasks.values())
            return max_priority
        
        return 5  # デフォルト優先度
    
    async def _notify_agent_adjustment(
        self,
        agent_id: str,
        resolution: ConflictResolution
    ) -> None:
        """エージェントに調整を通知"""
        adjustments = resolution.adjustments.get(agent_id, {})
        
        logger.info(f"エージェント {agent_id} に調整を通知: {adjustments}")
        
        # メッセージを作成して送信
        # （実際の実装では orchestrator 経由で送信）
    
    def add_coordination_rule(
        self,
        rule_type: str,
        **kwargs
    ) -> None:
        """調整ルールを追加"""
        rule = {
            "type": rule_type,
            **kwargs
        }
        self._coordination_rules.append(rule)
        
    def get_conflict_history(self) -> List[ConflictResolution]:
        """競合履歴を取得"""
        return self._conflict_history.copy()
    
    def get_agent_relationships(self) -> Dict[str, List[str]]:
        """エージェント間の関係を取得"""
        relationships = {}

        for agent_id in self._active_agents:
            relationships[agent_id] = []

            # 依存関係から関係を抽出
            for task_dep in self._task_dependencies.values():
                agent_tasks = self._active_agents[agent_id]["tasks"]
                if any(task.id == task_dep.task_id for task in agent_tasks.values()):
                    # このエージェントのタスクに依存している他のエージェントを探す
                    for other_agent, info in self._active_agents.items():
                        if other_agent != agent_id:
                            other_tasks = info["tasks"]
                            for dep_id in task_dep.depends_on:
                                if any(task.id == dep_id for task in other_tasks.values()):
                                    relationships[agent_id].append(other_agent)

        return relationships

    # === セキュリティ機能（POCから統合） ===

    async def check_security_risk(
        self,
        agent_id: str,
        action_description: str,
        target_environment: str = "",
    ) -> Dict[str, Any]:
        """
        エージェントのアクションに対するセキュリティリスクを評価

        危険なキーワードと保護対象環境のチェックを行い、
        自動的にブロックまたはエスカレーションします。

        Args:
            agent_id: アクションを実行するエージェントID
            action_description: アクションの説明
            target_environment: 対象環境名

        Returns:
            Dict[str, Any]: セキュリティ評価結果
        """
        action_lower = action_description.lower()
        env_lower = target_environment.lower()

        result = {
            "allowed": True,
            "risk_level": "low",
            "warnings": [],
            "blocked_reason": None,
        }

        # 危険キーワードチェック
        found_dangerous = [
            kw for kw in self.DANGEROUS_KEYWORDS if kw in action_lower
        ]
        if found_dangerous:
            result["warnings"].append(
                f"危険なキーワードを検出: {', '.join(found_dangerous)}"
            )
            result["risk_level"] = "high"

        # 保護対象環境チェック
        is_protected = any(env in env_lower for env in self.PROTECTED_ENVIRONMENTS)
        if is_protected and found_dangerous:
            result["allowed"] = False
            result["risk_level"] = "critical"
            result["blocked_reason"] = (
                f"保護対象環境 '{target_environment}' での危険な操作はブロックされました"
            )
            logger.warning(
                f"セキュリティブロック: エージェント {agent_id} の操作を拒否 - "
                f"{result['blocked_reason']}"
            )

        # エージェントタイプによる優先判定
        agent_info = self._active_agents.get(agent_id, {})
        agent_type = agent_info.get("agent_type", "")
        if agent_type == "security":
            # セキュリティエージェントは信頼度が高い
            if result["risk_level"] == "high":
                result["risk_level"] = "medium"
                result["warnings"].append(
                    "セキュリティエージェントによる操作のため信頼度を調整"
                )

        return result

    # === 学習機能（POCから統合） ===

    def record_resolution_outcome(
        self,
        conflict_type: ConflictType,
        strategy: str,
        success: bool,
    ) -> None:
        """
        競合解決の結果を記録し、将来の解決戦略の選択に活用

        Args:
            conflict_type: 競合タイプ
            strategy: 使用した解決戦略
            success: 解決が成功したかどうか
        """
        key = conflict_type.value
        if key not in self._resolution_success_rates:
            self._resolution_success_rates[key] = {}

        if strategy not in self._resolution_success_rates[key]:
            self._resolution_success_rates[key][strategy] = 0.5  # 初期値

        # 指数移動平均で更新
        current = self._resolution_success_rates[key][strategy]
        alpha = 0.3  # 学習率
        new_value = alpha * (1.0 if success else 0.0) + (1.0 - alpha) * current
        self._resolution_success_rates[key][strategy] = new_value

        logger.info(
            f"解決パターン学習: {conflict_type.value}/{strategy} -> "
            f"成功率 {new_value:.2f}"
        )

    def get_best_resolution_strategy(
        self,
        conflict_type: ConflictType,
    ) -> Optional[str]:
        """
        過去の学習データに基づいて最適な解決戦略を推薦

        Args:
            conflict_type: 競合タイプ

        Returns:
            Optional[str]: 推薦される解決戦略、またはNone
        """
        key = conflict_type.value
        strategies = self._resolution_success_rates.get(key, {})
        if not strategies:
            return None

        best_strategy = max(strategies, key=strategies.get)
        best_rate = strategies[best_strategy]

        if best_rate > 0.6:  # 成功率60%以上の場合のみ推薦
            return best_strategy
        return None

    def set_agent_type_priority(self, agent_type: str, priority: int) -> None:
        """
        エージェントタイプの優先度を設定

        Args:
            agent_type: エージェントタイプ
            priority: 優先度（0-100、高いほど優先）
        """
        self._agent_type_priorities[agent_type] = max(0, min(100, priority))

    def get_resolution_statistics(self) -> Dict[str, Any]:
        """解決パターンの学習統計を取得"""
        return {
            "success_rates": dict(self._resolution_success_rates),
            "total_conflicts_resolved": len(self._conflict_history),
            "agent_type_priorities": dict(self._agent_type_priorities),
            "active_agents": len(self._active_agents),
            "resource_locks": len(self._resource_locks),
        }
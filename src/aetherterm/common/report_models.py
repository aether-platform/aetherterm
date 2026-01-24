"""
レポートモデル定義

実行詳細レポートと時系列作業レポートのデータモデルを定義します。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
class ActivityType(str, Enum):
    """アクティビティタイプ"""

    COMMAND = "command"
    FILE_CREATE = "file_create"
    FILE_EDIT = "file_edit"
    FILE_DELETE = "file_delete"
    CODE_GENERATION = "code_generation"
    AGENT_ACTION = "agent_action"
    USER_INTERVENTION = "user_intervention"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
@dataclass
class ExecutionStep:
    """実行ステップの記録"""

    step_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    action: str = ""
    description: str = ""
    status: str = "success"  # success, failed, skipped
    duration_seconds: float = 0.0
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    screenshots: List[str] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)
@dataclass
class UserIntervention:
    """ユーザー介入記録"""

    intervention_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    type: str = "approval"
    message: str = ""
    options_presented: List[str] = field(default_factory=list)
    user_response: Optional[Any] = None
    response_time_seconds: Optional[float] = None
    timed_out: bool = False
@dataclass
class AgentExecution:
    """エージェント実行の記録"""

    agent_id: str = ""
    agent_type: str = ""
    task_id: UUID = field(default_factory=uuid4)
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    status: str = "running"
    steps: List[ExecutionStep] = field(default_factory=list)
    interventions: List[UserIntervention] = field(default_factory=list)
    resource_usage: Dict[str, float] = field(default_factory=dict)
@dataclass
class ExecutionReport:
    """実行詳細レポート"""

    report_id: UUID = field(default_factory=uuid4)
    session_id: str = ""
    title: str = ""
    description: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    total_duration_seconds: float = 0.0

    # 実行サマリー
    task_summary: Dict[str, Any] = field(default_factory=dict)
    success_rate: float = 0.0
    total_steps: int = 0
    failed_steps: int = 0

    # エージェント実行詳細
    agent_executions: List[AgentExecution] = field(default_factory=list)

    # ユーザー介入
    total_interventions: int = 0
    intervention_details: List[Dict[str, Any]] = field(default_factory=list)

    # 成果物
    artifacts: Dict[str, Any] = field(default_factory=dict)
    generated_files: List[str] = field(default_factory=list)
    modified_files: List[str] = field(default_factory=list)

    # メトリクス
    performance_metrics: Dict[str, float] = field(default_factory=dict)
    resource_metrics: Dict[str, float] = field(default_factory=dict)

    # エラーと警告
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "report_id": str(self.report_id),
            "session_id": self.session_id,
            "title": self.title,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "total_duration_seconds": self.total_duration_seconds,
            "task_summary": self.task_summary,
            "success_rate": self.success_rate,
            "total_steps": self.total_steps,
            "failed_steps": self.failed_steps,
            "agent_executions": [
                {
                    "agent_id": ae.agent_id,
                    "agent_type": ae.agent_type,
                    "task_id": str(ae.task_id),
                    "started_at": ae.started_at.isoformat(),
                    "completed_at": ae.completed_at.isoformat() if ae.completed_at else None,
                    "status": ae.status,
                    "steps": len(ae.steps),
                    "interventions": len(ae.interventions),
                    "resource_usage": ae.resource_usage,
                }
                for ae in self.agent_executions
            ],
            "total_interventions": self.total_interventions,
            "artifacts": self.artifacts,
            "generated_files": self.generated_files,
            "modified_files": self.modified_files,
            "performance_metrics": self.performance_metrics,
            "resource_metrics": self.resource_metrics,
            "errors": self.errors,
            "warnings": self.warnings,
        }
@dataclass
class WorkActivity:
    """作業アクティビティ"""

    timestamp: datetime = field(default_factory=datetime.utcnow)
    activity_type: ActivityType = ActivityType.INFO
    title: str = ""
    description: str = ""
    agent_id: Optional[str] = None

    # コマンド関連
    command: Optional[str] = None
    exit_code: Optional[int] = None

    # ファイル操作関連
    file_path: Optional[str] = None
    file_action: Optional[str] = None
    diff: Optional[str] = None

    # 生成物
    generated_content: Optional[str] = None

    # メタデータ
    duration_seconds: Optional[float] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "activity_type": self.activity_type.value,
            "title": self.title,
            "description": self.description,
            "agent_id": self.agent_id,
            "command": self.command,
            "exit_code": self.exit_code,
            "file_path": self.file_path,
            "file_action": self.file_action,
            "duration_seconds": self.duration_seconds,
            "tags": self.tags,
            "metadata": self.metadata,
        }
@dataclass
class WorkSection:
    """作業セクション（関連する作業のグループ）"""

    section_id: UUID = field(default_factory=uuid4)
    title: str = ""
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    activities: List[WorkActivity] = field(default_factory=list)
    summary: str = ""
    goal_achieved: bool = False

    def add_activity(self, activity: WorkActivity) -> None:
        """アクティビティを追加"""
        self.activities.append(activity)
        if not self.completed_at:
            self.completed_at = activity.timestamp

    def get_duration_seconds(self) -> float:
        """セクションの実行時間を取得"""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0
@dataclass
class TimelineReport:
    """時系列作業レポート"""

    report_id: UUID = field(default_factory=uuid4)
    session_id: str = ""
    title: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    period_start: datetime = field(default_factory=datetime.utcnow)
    period_end: datetime = field(default_factory=datetime.utcnow)

    # 作業サマリー
    total_activities: int = 0
    total_commands: int = 0
    files_created: int = 0
    files_modified: int = 0
    total_duration_seconds: float = 0.0

    # 時系列データ
    work_sections: List[WorkSection] = field(default_factory=list)
    raw_activities: List[WorkActivity] = field(default_factory=list)

    # 成果サマリー
    key_achievements: List[str] = field(default_factory=list)
    problems_encountered: List[str] = field(default_factory=list)
    next_steps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "report_id": str(self.report_id),
            "session_id": self.session_id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "total_activities": self.total_activities,
            "total_commands": self.total_commands,
            "files_created": self.files_created,
            "files_modified": self.files_modified,
            "total_duration_seconds": self.total_duration_seconds,
            "work_sections": [
                {
                    "section_id": str(section.section_id),
                    "title": section.title,
                    "started_at": section.started_at.isoformat(),
                    "completed_at": section.completed_at.isoformat()
                    if section.completed_at
                    else None,
                    "activities_count": len(section.activities),
                    "summary": section.summary,
                    "goal_achieved": section.goal_achieved,
                }
                for section in self.work_sections
            ],
            "total_activities": len(self.raw_activities),
            "key_achievements": self.key_achievements,
            "problems_encountered": self.problems_encountered,
            "next_steps": self.next_steps,
        }

    def add_activity(self, activity: WorkActivity) -> None:
        """アクティビティを追加"""
        self.raw_activities.append(activity)

        # 統計を更新
        if activity.activity_type == ActivityType.COMMAND:
            self.total_commands += 1
        elif activity.activity_type == ActivityType.FILE_CREATE:
            self.files_created += 1
        elif activity.activity_type == ActivityType.FILE_EDIT:
            self.files_modified += 1

        self.total_activities = len(self.raw_activities)

        # 期間を更新
        if activity.timestamp < self.period_start:
            self.period_start = activity.timestamp
        if activity.timestamp > self.period_end:
            self.period_end = activity.timestamp

        # 総実行時間を更新
        self.total_duration_seconds = (self.period_end - self.period_start).total_seconds()
class ReportType(str, Enum):
    """レポートタイプ"""

    EXECUTION_DETAIL = "execution_detail"
    TIMELINE_ACTIVITY = "timeline_activity"

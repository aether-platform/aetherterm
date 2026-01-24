"""
オペレーションコンテキスト推定用のモデル定義
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
class OperationType(Enum):
    """オペレーションタイプ"""

    DEPLOYMENT = "deployment"
    DEBUGGING = "debugging"
    DEVELOPMENT = "development"
    TESTING = "testing"
    MAINTENANCE = "maintenance"
    INVESTIGATION = "investigation"
    SETUP = "setup"
    UNKNOWN = "unknown"
class OperationStage(Enum):
    """オペレーション段階"""

    STARTING = "starting"
    IN_PROGRESS = "in_progress"
    VALIDATING = "validating"
    COMPLETING = "completing"
    FAILED = "failed"
    COMPLETED = "completed"
@dataclass
class CommandPattern:
    """コマンドパターン"""

    command: str
    context: str
    frequency: int
    success_rate: float
    typical_duration: float
    next_commands: List[str] = field(default_factory=list)
@dataclass
class OperationContext:
    """オペレーションコンテキスト"""

    terminal_id: str
    operation_type: OperationType
    stage: OperationStage
    confidence: float
    start_time: datetime
    estimated_duration: Optional[float] = None
    progress_percentage: float = 0.0

    # コマンド履歴
    command_sequence: List[str] = field(default_factory=list)

    # 予測
    next_likely_commands: List[str] = field(default_factory=list)
    estimated_completion_time: Optional[datetime] = None

    # リスク分析
    risk_factors: List[str] = field(default_factory=list)
    failure_probability: float = 0.0

    # 関連情報
    similar_operations: List[str] = field(default_factory=list)
    suggested_actions: List[str] = field(default_factory=list)

    # メタデータ
    metadata: Dict[str, Any] = field(default_factory=dict)
@dataclass
class OperationPattern:
    """学習済みオペレーションパターン"""

    pattern_id: str
    operation_type: OperationType
    name: str
    description: str

    # パターン定義
    command_sequence: List[str]
    success_indicators: List[str]
    failure_indicators: List[str]

    # 統計情報
    frequency: int
    success_rate: float
    average_duration: float

    # コンテキスト
    typical_triggers: List[str]
    dependencies: List[str]
    environment: Dict[str, str]

    # 学習データ
    embedding: Optional[List[float]] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
@dataclass
class ContextInferenceResult:
    """コンテキスト推定結果"""

    terminal_id: str
    timestamp: datetime

    # 推定結果
    primary_context: OperationContext
    alternative_contexts: List[OperationContext] = field(default_factory=list)

    # 信頼度
    overall_confidence: float = 0.0

    # 推定根拠
    reasoning: List[str] = field(default_factory=list)
    matched_patterns: List[str] = field(default_factory=list)

    # 推薦
    recommendations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
@dataclass
class TeamOperationContext:
    """チームオペレーションコンテキスト"""

    project_id: str
    operation_type: OperationType
    start_time: datetime

    # 参加者
    participants: List[str] = field(default_factory=list)
    lead_terminal: Optional[str] = None

    # 協調パターン
    coordination_level: str = "independent"  # independent, coordinated, collaborative
    shared_context: Dict[str, Any] = field(default_factory=dict)

    # 進捗
    individual_progress: Dict[str, float] = field(default_factory=dict)
    overall_progress: float = 0.0

    # 同期ポイント
    sync_points: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)

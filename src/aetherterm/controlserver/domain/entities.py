"""
ドメインエンティティ

ControlServerの純粋なビジネスモデルを定義します。
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class BlockCommand:
    """ブロックコマンド記録"""

    block_id: str
    block_type: str  # "admin_initiated", "auto_detected", "emergency"
    reason: str
    admin_user: Optional[str]
    affected_sessions: List[str]
    timestamp: str
    expires_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentInfo:
    """接続エージェント情報"""

    agent_id: str
    status: str
    active_sessions: int
    last_heartbeat: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SessionInfo:
    """セッション情報"""

    session_id: str
    agent_server_id: str
    user_info: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    last_activity: str = ""
    is_blocked: bool = False
    block_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

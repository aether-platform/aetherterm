"""
ドメインエンティティ

フレームワーク非依存の純粋なビジネスモデルを定義します。
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class BlockReason(str, Enum):
    """ブロック理由"""

    CRITICAL_KEYWORD = "critical_keyword"
    MULTIPLE_WARNINGS = "multiple_warnings"
    MANUAL_BLOCK = "manual_block"
    SYSTEM_PROTECTION = "system_protection"


class SeverityLevel(str, Enum):
    """危険度レベル"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SessionOwner:
    """セッション所有者情報"""

    remote_addr: Optional[str] = None
    remote_user: Optional[str] = None
    user_name: Optional[str] = None
    created_at: float = field(default_factory=time.time)


@dataclass
class BlockState:
    """セッションのブロック状態"""

    session_id: str
    is_blocked: bool
    reason: BlockReason
    message: str
    alert_message: str
    detected_keywords: List[str] = field(default_factory=list)
    blocked_at: float = field(default_factory=time.time)
    unlock_key: str = "ctrl_d"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "auto_block",
            "session_id": self.session_id,
            "severity": _severity_from_reason(self.reason),
            "message": self.message,
            "detected_keywords": self.detected_keywords,
            "alert_message": self.alert_message,
            "unlock_key": self.unlock_key,
            "timestamp": self.blocked_at,
        }


@dataclass
class DetectionResult:
    """脅威検出結果"""

    severity: SeverityLevel
    detected_keywords: List[str]
    message: str
    should_block: bool
    alert_message: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class UserInfo:
    """接続ユーザー情報"""

    remote_addr: Optional[str] = None
    remote_user: Optional[str] = None
    forwarded_for: Optional[str] = None
    user_agent: Optional[str] = None


@dataclass
class TerminalSessionInfo:
    """ターミナルセッション情報（ドメインビュー）"""

    session_id: str
    client_sids: Set[str] = field(default_factory=set)
    is_closed: bool = False
    owner: Optional[SessionOwner] = None
    history: str = ""


def _severity_from_reason(reason: BlockReason) -> str:
    """ブロック理由から危険度を取得"""
    severity_map = {
        BlockReason.CRITICAL_KEYWORD: "critical",
        BlockReason.MULTIPLE_WARNINGS: "high",
        BlockReason.MANUAL_BLOCK: "medium",
        BlockReason.SYSTEM_PROTECTION: "critical",
    }
    return severity_map.get(reason, "medium")


def check_session_ownership(owner: Optional[SessionOwner], user_info: UserInfo) -> bool:
    """セッション所有権を確認"""
    if owner is None:
        return False

    # X-REMOTE-USER ヘッダーで比較（認証済みユーザーに最も信頼性が高い）
    if user_info.remote_user and owner.remote_user and user_info.remote_user == owner.remote_user:
        return True

    # IPアドレスで比較（フォールバック）
    if user_info.remote_addr and owner.remote_addr and user_info.remote_addr == owner.remote_addr:
        return True

    return False

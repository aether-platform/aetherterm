"""
Security threat detector for ControlServer.

Analyzes terminal input events in real-time to detect dangerous commands,
privilege escalation attempts, data exfiltration, and other security threats.
Publishes alerts via NATS when threats are detected.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ThreatSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ThreatCategory(str, Enum):
    DESTRUCTIVE_COMMAND = "destructive_command"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    DATA_EXFILTRATION = "data_exfiltration"
    NETWORK_ATTACK = "network_attack"
    SYSTEM_TAMPERING = "system_tampering"
    CREDENTIAL_ACCESS = "credential_access"
    SUSPICIOUS_PATTERN = "suspicious_pattern"


@dataclass
class ThreatAlert:
    """Detected threat alert."""

    session_id: str
    agent_id: str
    command: str
    category: ThreatCategory
    severity: ThreatSeverity
    description: str
    matched_patterns: List[str]
    timestamp: str
    auto_block: bool = False


@dataclass
class _ThreatPattern:
    """Internal threat pattern definition."""

    pattern: re.Pattern
    category: ThreatCategory
    severity: ThreatSeverity
    description: str
    auto_block: bool = False


# Pre-compiled threat patterns
_PATTERNS: List[_ThreatPattern] = [
    # --- CRITICAL: Auto-block ---
    _ThreatPattern(
        re.compile(r"rm\s+(-[rf]+\s+)?/\s*$|rm\s+-[rf]+\s+/(?:etc|var|usr|boot|home)\b"),
        ThreatCategory.DESTRUCTIVE_COMMAND,
        ThreatSeverity.CRITICAL,
        "Recursive deletion of system directories",
        auto_block=True,
    ),
    _ThreatPattern(
        re.compile(r"mkfs\b|dd\s+.*\bof=/dev/[sh]d[a-z]\b"),
        ThreatCategory.DESTRUCTIVE_COMMAND,
        ThreatSeverity.CRITICAL,
        "Disk format or overwrite",
        auto_block=True,
    ),
    _ThreatPattern(
        re.compile(r":\(\)\{\s*:\|:\s*&\s*\}\s*;|fork\s*bomb", re.IGNORECASE),
        ThreatCategory.DESTRUCTIVE_COMMAND,
        ThreatSeverity.CRITICAL,
        "Fork bomb detected",
        auto_block=True,
    ),
    # --- HIGH ---
    _ThreatPattern(
        re.compile(r"chmod\s+[0-7]*777\s+/|chmod\s+-R\s+777"),
        ThreatCategory.SYSTEM_TAMPERING,
        ThreatSeverity.HIGH,
        "Dangerous permission change (777)",
    ),
    _ThreatPattern(
        re.compile(r"passwd\s+root|usermod\s+.*-aG\s+sudo|visudo"),
        ThreatCategory.PRIVILEGE_ESCALATION,
        ThreatSeverity.HIGH,
        "Privilege escalation attempt",
    ),
    _ThreatPattern(
        re.compile(r"curl\s+.*\|\s*(ba)?sh|wget\s+.*\|\s*(ba)?sh"),
        ThreatCategory.SYSTEM_TAMPERING,
        ThreatSeverity.HIGH,
        "Remote script execution (pipe to shell)",
    ),
    _ThreatPattern(
        re.compile(r"iptables\s+-F|ufw\s+disable|firewall-cmd\s+.*--remove"),
        ThreatCategory.NETWORK_ATTACK,
        ThreatSeverity.HIGH,
        "Firewall rule removal",
    ),
    _ThreatPattern(
        re.compile(r"/etc/shadow|/etc/passwd.*:\s*\$"),
        ThreatCategory.CREDENTIAL_ACCESS,
        ThreatSeverity.HIGH,
        "Credential file access",
    ),
    # --- MEDIUM ---
    _ThreatPattern(
        re.compile(r"nc\s+-[le]|ncat\s+-[le]|socat\s+.*EXEC"),
        ThreatCategory.NETWORK_ATTACK,
        ThreatSeverity.MEDIUM,
        "Reverse shell / bind shell attempt",
    ),
    _ThreatPattern(
        re.compile(r"scp\s+.*@|rsync\s+.*@|curl\s+.*-T\s|curl\s+.*--upload"),
        ThreatCategory.DATA_EXFILTRATION,
        ThreatSeverity.MEDIUM,
        "Data exfiltration attempt",
    ),
    _ThreatPattern(
        re.compile(r"crontab\s+-[er]|systemctl\s+(enable|start)\s+"),
        ThreatCategory.SYSTEM_TAMPERING,
        ThreatSeverity.MEDIUM,
        "Service/cron modification",
    ),
    _ThreatPattern(
        re.compile(r"history\s+-c|unset\s+HISTFILE|export\s+HISTSIZE=0"),
        ThreatCategory.SUSPICIOUS_PATTERN,
        ThreatSeverity.MEDIUM,
        "History tampering",
    ),
    # --- LOW ---
    _ThreatPattern(
        re.compile(r"sudo\s+su\b|sudo\s+-i\b|sudo\s+bash\b"),
        ThreatCategory.PRIVILEGE_ESCALATION,
        ThreatSeverity.LOW,
        "Root shell access",
    ),
    _ThreatPattern(
        re.compile(r"nmap\s|masscan\s|nikto\s"),
        ThreatCategory.NETWORK_ATTACK,
        ThreatSeverity.LOW,
        "Network scanning tool usage",
    ),
]


class ThreatDetector:
    """Real-time security threat detector for terminal commands."""

    def __init__(self, nats_client=None):
        self._nats = nats_client
        self._alerts: List[ThreatAlert] = []
        self._alert_counts: Dict[str, int] = {}  # session_id -> count
        self._total_analyzed = 0

    def set_nats_client(self, nats_client) -> None:
        """Set NATS client for publishing alerts."""
        self._nats = nats_client

    async def analyze_input(self, subject: str, data: Dict[str, Any]) -> Optional[ThreatAlert]:
        """Analyze a terminal input event for threats.

        Returns the alert if a threat was detected, None otherwise.
        """
        content = data.get("content", "")
        session_id = data.get("session_id", "")
        agent_id = data.get("agent_id", "")
        timestamp = data.get("timestamp", datetime.now().isoformat())

        if not content.strip():
            return None

        self._total_analyzed += 1
        command = content.strip()

        matched = []
        highest_severity = None
        highest_alert = None

        for tp in _PATTERNS:
            if tp.pattern.search(command):
                matched.append(tp)
                if highest_severity is None or _severity_rank(tp.severity) > _severity_rank(
                    highest_severity
                ):
                    highest_severity = tp.severity
                    highest_alert = tp

        if not matched:
            return None

        alert = ThreatAlert(
            session_id=session_id,
            agent_id=agent_id,
            command=command,
            category=highest_alert.category,
            severity=highest_alert.severity,
            description=highest_alert.description,
            matched_patterns=[tp.description for tp in matched],
            timestamp=timestamp,
            auto_block=any(tp.auto_block for tp in matched),
        )

        self._alerts.append(alert)
        self._alert_counts[session_id] = self._alert_counts.get(session_id, 0) + 1

        logger.warning(
            f"[THREAT] {alert.severity.value.upper()} - {alert.description} "
            f"session={session_id} command='{command[:80]}'"
        )

        # Publish alert via NATS
        if self._nats:
            from ...common.nats import Subjects

            await self._nats.publish(
                Subjects.control_alert(alert.severity.value),
                {
                    "session_id": alert.session_id,
                    "agent_id": alert.agent_id,
                    "command": alert.command,
                    "category": alert.category.value,
                    "severity": alert.severity.value,
                    "description": alert.description,
                    "matched_patterns": alert.matched_patterns,
                    "auto_block": alert.auto_block,
                    "timestamp": alert.timestamp,
                },
            )

            # Auto-block: send block command to the agent
            if alert.auto_block:
                await self._nats.publish(
                    Subjects.control_command(agent_id),
                    {
                        "command": "block_session",
                        "session_id": session_id,
                        "message": f"Auto-blocked: {alert.description}",
                        "severity": alert.severity.value,
                        "timestamp": datetime.now().isoformat(),
                    },
                )
                logger.warning(f"Auto-block sent for session {session_id}")

        return alert

    def get_alerts(
        self,
        session_id: Optional[str] = None,
        severity: Optional[ThreatSeverity] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get recent alerts, optionally filtered."""
        alerts = self._alerts
        if session_id:
            alerts = [a for a in alerts if a.session_id == session_id]
        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        return [
            {
                "session_id": a.session_id,
                "agent_id": a.agent_id,
                "command": a.command,
                "category": a.category.value,
                "severity": a.severity.value,
                "description": a.description,
                "matched_patterns": a.matched_patterns,
                "auto_block": a.auto_block,
                "timestamp": a.timestamp,
            }
            for a in alerts[-limit:]
        ]

    def get_statistics(self) -> Dict[str, Any]:
        """Get threat detection statistics."""
        severity_counts = {}
        for a in self._alerts:
            severity_counts[a.severity.value] = severity_counts.get(a.severity.value, 0) + 1

        return {
            "total_commands_analyzed": self._total_analyzed,
            "total_threats_detected": len(self._alerts),
            "threats_by_severity": severity_counts,
            "sessions_with_alerts": len(self._alert_counts),
            "alert_counts_by_session": dict(self._alert_counts),
        }


def _severity_rank(severity: ThreatSeverity) -> int:
    return {
        ThreatSeverity.LOW: 1,
        ThreatSeverity.MEDIUM: 2,
        ThreatSeverity.HIGH: 3,
        ThreatSeverity.CRITICAL: 4,
    }.get(severity, 0)

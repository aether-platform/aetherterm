"""
コマンド脅威解析ドメインサービス

ターミナル出力・コマンドのパターンマッチングによる脅威検出を行う
純粋なビジネスロジック（フレームワーク非依存）。
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ThreatLevel(str, Enum):
    """脅威レベル"""

    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ThreatAnalysisResult:
    """脅威解析結果"""

    threat_level: ThreatLevel
    confidence: float
    detected_keywords: List[str] = field(default_factory=list)
    message: str = ""
    should_block: bool = False


class CommandThreatAnalyzer:
    """コマンド脅威解析サービス（ドメインサービス）"""

    DANGEROUS_PATTERNS: Dict[str, List[str]] = {
        "system_destruction": [
            "rm -rf /",
            "rm -rf /*",
            "mkfs",
            "dd if=/dev/zero",
            ":(){ :|:& };:",
            "> /dev/sda",
            "chmod -R 777 /",
        ],
        "security_risk": [
            "passwd",
            "shadow",
            "sudoers",
            "ssh-keygen",
            "authorized_keys",
            "id_rsa",
        ],
        "network_attack": [
            "nmap",
            "netcat",
            "nc -l",
            "tcpdump",
            "wireshark",
            "arp-scan",
            "masscan",
        ],
        "data_leakage": [
            "curl.*|.*sh",
            "wget.*|.*sh",
            "base64",
            "xxd",
            "exfiltrat",
        ],
    }

    WARNING_PATTERNS: List[str] = [
        "sudo",
        "su -",
        "chmod",
        "chown",
        "iptables",
        "kill",
        "pkill",
    ]

    def __init__(
        self,
        custom_dangerous_patterns: Optional[Dict[str, List[str]]] = None,
        custom_warning_patterns: Optional[List[str]] = None,
    ):
        self._dangerous_patterns = dict(self.DANGEROUS_PATTERNS)
        if custom_dangerous_patterns:
            for category, patterns in custom_dangerous_patterns.items():
                self._dangerous_patterns.setdefault(category, []).extend(patterns)

        self._warning_patterns = list(self.WARNING_PATTERNS)
        if custom_warning_patterns:
            self._warning_patterns.extend(custom_warning_patterns)

    def analyze(self, text: str) -> ThreatAnalysisResult:
        """テキストを解析し、脅威レベルを判定"""
        if not text or not text.strip():
            return ThreatAnalysisResult(
                threat_level=ThreatLevel.SAFE, confidence=1.0
            )

        text_lower = text.lower()
        detected_keywords: List[str] = []
        max_threat = ThreatLevel.SAFE

        # 危険パターンチェック
        for category, patterns in self._dangerous_patterns.items():
            for pattern in patterns:
                if pattern.lower() in text_lower:
                    detected_keywords.append(f"{category}:{pattern}")
                    if category == "system_destruction":
                        max_threat = ThreatLevel.CRITICAL
                    elif max_threat != ThreatLevel.CRITICAL:
                        max_threat = ThreatLevel.HIGH

        # 警告パターンチェック
        for pattern in self._warning_patterns:
            if pattern.lower() in text_lower:
                detected_keywords.append(f"warning:{pattern}")
                if max_threat in (ThreatLevel.SAFE, ThreatLevel.LOW):
                    max_threat = ThreatLevel.MEDIUM

        if not detected_keywords:
            return ThreatAnalysisResult(
                threat_level=ThreatLevel.SAFE, confidence=1.0
            )

        should_block = max_threat in (ThreatLevel.HIGH, ThreatLevel.CRITICAL)
        confidence = min(0.5 + len(detected_keywords) * 0.1, 1.0)

        return ThreatAnalysisResult(
            threat_level=max_threat,
            confidence=confidence,
            detected_keywords=detected_keywords,
            message=f"Detected {len(detected_keywords)} threat patterns: {', '.join(detected_keywords[:5])}",
            should_block=should_block,
        )

    def is_dangerous(self, command: str) -> bool:
        """コマンドが危険かどうかを簡易判定"""
        result = self.analyze(command)
        return result.threat_level in (ThreatLevel.HIGH, ThreatLevel.CRITICAL)

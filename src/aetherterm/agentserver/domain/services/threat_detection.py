"""
脅威検出ドメインサービス

ターミナル出力のリアルタイム解析と危険度判定を行う
純粋なビジネスロジック（フレームワーク非依存）。
"""

import logging
import time
from typing import Dict, List, Optional

from ..entities import DetectionResult, SeverityLevel

logger = logging.getLogger(__name__)


class ThreatDetectionService:
    """脅威検出サービス（ドメインサービス）"""

    def __init__(
        self,
        critical_keywords: Optional[List[str]] = None,
        warning_keywords: Optional[List[str]] = None,
        critical_keyword_threshold: int = 1,
        warning_keyword_threshold: int = 3,
        time_window_seconds: int = 30,
    ):
        self.critical_keywords = critical_keywords or [
            "rm -rf",
            "sudo rm",
            "format",
            "mkfs",
            "hack",
            "attack",
            "exploit",
            "malware",
            "critical",
            "fatal",
            "emergency",
            "security",
        ]

        self.warning_keywords = warning_keywords or [
            "error",
            "fail",
            "warning",
            "denied",
            "unauthorized",
            "forbidden",
            "timeout",
        ]

        self._critical_threshold = critical_keyword_threshold
        self._warning_threshold = warning_keyword_threshold
        self._time_window = time_window_seconds

        # セッション別検出履歴
        self._session_history: Dict[str, List[DetectionResult]] = {}

    def analyze_output(self, session_id: str, output: str) -> Optional[DetectionResult]:
        """
        ターミナル出力を解析し、脅威を検出

        Args:
            session_id: セッションID
            output: ターミナル出力文字列

        Returns:
            DetectionResult if threat detected, None otherwise
        """
        if not output or not output.strip():
            return None

        output_lower = output.lower()
        detected_keywords: List[str] = []

        critical_found = [kw for kw in self.critical_keywords if kw.lower() in output_lower]
        detected_keywords.extend(critical_found)

        warning_found = [kw for kw in self.warning_keywords if kw.lower() in output_lower]
        detected_keywords.extend(warning_found)

        if not detected_keywords:
            return None

        # 危険度判定
        if critical_found:
            result = DetectionResult(
                severity=SeverityLevel.CRITICAL,
                detected_keywords=detected_keywords,
                message=f"クリティカルキーワードが検出されました: {', '.join(critical_found)}",
                should_block=True,
                alert_message="!!!CRITICAL ALERT!!! Ctrl+Dを押して確認してください",
            )
        elif len(warning_found) >= self._warning_threshold:
            result = DetectionResult(
                severity=SeverityLevel.HIGH,
                detected_keywords=detected_keywords,
                message=f"複数の警告キーワードが検出されました: {', '.join(warning_found)}",
                should_block=True,
                alert_message="!!!WARNING ALERT!!! Ctrl+Dを押して確認してください",
            )
        elif warning_found:
            result = DetectionResult(
                severity=SeverityLevel.MEDIUM,
                detected_keywords=detected_keywords,
                message=f"警告キーワードが検出されました: {', '.join(warning_found)}",
                should_block=False,
                alert_message="",
            )
        else:
            return None

        # 履歴に追加
        if session_id not in self._session_history:
            self._session_history[session_id] = []
        self._session_history[session_id].append(result)
        self._cleanup_old_history(session_id)

        return result

    def get_session_risk_level(self, session_id: str) -> SeverityLevel:
        """セッションの現在のリスクレベルを取得"""
        history = self._session_history.get(session_id, [])
        if not history:
            return SeverityLevel.LOW

        max_severity = SeverityLevel.LOW
        for result in history:
            if result.severity == SeverityLevel.CRITICAL:
                return SeverityLevel.CRITICAL
            if result.severity == SeverityLevel.HIGH:
                max_severity = SeverityLevel.HIGH
            elif result.severity == SeverityLevel.MEDIUM and max_severity == SeverityLevel.LOW:
                max_severity = SeverityLevel.MEDIUM

        return max_severity

    def get_statistics(self, session_id: str) -> Dict:
        """セッションの統計情報を取得"""
        history = self._session_history.get(session_id, [])
        if not history:
            return {
                "total_detections": 0,
                "critical_count": 0,
                "high_count": 0,
                "medium_count": 0,
                "last_detection": None,
            }

        return {
            "total_detections": len(history),
            "critical_count": sum(1 for r in history if r.severity == SeverityLevel.CRITICAL),
            "high_count": sum(1 for r in history if r.severity == SeverityLevel.HIGH),
            "medium_count": sum(1 for r in history if r.severity == SeverityLevel.MEDIUM),
            "last_detection": max(r.timestamp for r in history),
        }

    def add_custom_keyword(self, keyword: str, severity: SeverityLevel) -> None:
        """カスタムキーワードを追加"""
        if severity == SeverityLevel.CRITICAL:
            if keyword not in self.critical_keywords:
                self.critical_keywords.append(keyword)
        elif severity in (SeverityLevel.MEDIUM, SeverityLevel.HIGH):
            if keyword not in self.warning_keywords:
                self.warning_keywords.append(keyword)

    def remove_custom_keyword(self, keyword: str) -> None:
        """カスタムキーワードを削除"""
        if keyword in self.critical_keywords:
            self.critical_keywords.remove(keyword)
        if keyword in self.warning_keywords:
            self.warning_keywords.remove(keyword)

    def _cleanup_old_history(self, session_id: str) -> None:
        """古い検出履歴をクリーンアップ"""
        if session_id not in self._session_history:
            return
        current_time = time.time()
        self._session_history[session_id] = [
            r for r in self._session_history[session_id] if current_time - r.timestamp <= self._time_window
        ]

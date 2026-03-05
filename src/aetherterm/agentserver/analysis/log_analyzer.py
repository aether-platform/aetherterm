"""リアルタイムログ解析機能
ターミナル出力をリアルタイムで監視し、危険なキーワードを検出する
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

log = logging.getLogger("aetherterm.log_analyzer")


class SeverityLevel(Enum):
    """危険度レベル"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class DetectionResult:
    """検出結果"""

    severity: SeverityLevel
    detected_keywords: List[str]
    message: str
    should_block: bool
    alert_message: str
    timestamp: float


class LogAnalyzer:
    """リアルタイムログ解析クラス"""

    def __init__(self):
        self.critical_keywords = [
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

        self.warning_keywords = [
            "error",
            "fail",
            "warning",
            "denied",
            "unauthorized",
            "forbidden",
            "timeout",
        ]

        # 自動ブロック条件
        self.auto_block_conditions = {
            "critical_keyword_count": 1,  # クリティカル1個で即ブロック
            "warning_keyword_threshold": 3,  # 警告3個でブロック
            "time_window": 30,  # 30秒間の監視ウィンドウ
        }

        # セッション別の検出履歴
        self.session_history: Dict[str, List[DetectionResult]] = {}

    def analyze_output(self, session_id: str, output: str) -> Optional[DetectionResult]:
        """ターミナル出力を解析し、危険度を判定

        Args:
            session_id: セッションID
            output: ターミナル出力文字列

        Returns:
            DetectionResult: 検出結果（危険でない場合はNone）
        """
        if not output or not output.strip():
            return None

        output_lower = output.lower()
        detected_keywords = []
        severity = SeverityLevel.LOW

        # クリティカルキーワードの検出
        critical_found = []
        for keyword in self.critical_keywords:
            if keyword.lower() in output_lower:
                critical_found.append(keyword)
                detected_keywords.append(keyword)

        # 警告キーワードの検出
        warning_found = []
        for keyword in self.warning_keywords:
            if keyword.lower() in output_lower:
                warning_found.append(keyword)
                detected_keywords.append(keyword)

        if not detected_keywords:
            return None

        # 危険度判定
        if critical_found:
            severity = SeverityLevel.CRITICAL
            message = f"クリティカルキーワードが検出されました: {', '.join(critical_found)}"
            should_block = True
            alert_message = "!!!CRITICAL ALERT!!! Ctrl+Dを押して確認してください"
        elif len(warning_found) >= self.auto_block_conditions["warning_keyword_threshold"]:
            severity = SeverityLevel.HIGH
            message = f"複数の警告キーワードが検出されました: {', '.join(warning_found)}"
            should_block = True
            alert_message = "!!!WARNING ALERT!!! Ctrl+Dを押して確認してください"
        elif warning_found:
            severity = SeverityLevel.MEDIUM
            message = f"警告キーワードが検出されました: {', '.join(warning_found)}"
            should_block = False
            alert_message = ""
        else:
            return None

        result = DetectionResult(
            severity=severity,
            detected_keywords=detected_keywords,
            message=message,
            should_block=should_block,
            alert_message=alert_message,
            timestamp=time.time(),
        )

        # セッション履歴に追加
        if session_id not in self.session_history:
            self.session_history[session_id] = []
        self.session_history[session_id].append(result)

        # 古い履歴をクリーンアップ（30秒以上前）
        self._cleanup_old_history(session_id)

        log.info(f"Log analysis result for session {session_id}: {severity.value} - {message}")

        return result

    def _cleanup_old_history(self, session_id: str):
        """古い検出履歴をクリーンアップ"""
        if session_id not in self.session_history:
            return

        current_time = time.time()
        time_window = self.auto_block_conditions["time_window"]

        self.session_history[session_id] = [
            result
            for result in self.session_history[session_id]
            if current_time - result.timestamp <= time_window
        ]

    def get_session_risk_level(self, session_id: str) -> SeverityLevel:
        """セッションの現在のリスクレベルを取得"""
        if session_id not in self.session_history:
            return SeverityLevel.LOW

        recent_results = self.session_history[session_id]
        if not recent_results:
            return SeverityLevel.LOW

        # 最も高い危険度を返す
        max_severity = SeverityLevel.LOW
        for result in recent_results:
            if result.severity == SeverityLevel.CRITICAL:
                return SeverityLevel.CRITICAL
            if result.severity == SeverityLevel.HIGH:
                max_severity = SeverityLevel.HIGH
            elif result.severity == SeverityLevel.MEDIUM and max_severity == SeverityLevel.LOW:
                max_severity = SeverityLevel.MEDIUM

        return max_severity

    def add_custom_keyword(self, keyword: str, severity: SeverityLevel):
        """カスタムキーワードを追加"""
        if severity == SeverityLevel.CRITICAL:
            if keyword not in self.critical_keywords:
                self.critical_keywords.append(keyword)
        elif severity in [SeverityLevel.MEDIUM, SeverityLevel.HIGH]:
            if keyword not in self.warning_keywords:
                self.warning_keywords.append(keyword)

        log.info(f"Added custom keyword: {keyword} with severity {severity.value}")

    def remove_custom_keyword(self, keyword: str):
        """カスタムキーワードを削除"""
        if keyword in self.critical_keywords:
            self.critical_keywords.remove(keyword)
        if keyword in self.warning_keywords:
            self.warning_keywords.remove(keyword)

        log.info(f"Removed custom keyword: {keyword}")

    def get_statistics(self, session_id: str) -> Dict:
        """セッションの統計情報を取得"""
        if session_id not in self.session_history:
            return {
                "total_detections": 0,
                "critical_count": 0,
                "high_count": 0,
                "medium_count": 0,
                "last_detection": None,
            }

        history = self.session_history[session_id]
        stats = {
            "total_detections": len(history),
            "critical_count": sum(1 for r in history if r.severity == SeverityLevel.CRITICAL),
            "high_count": sum(1 for r in history if r.severity == SeverityLevel.HIGH),
            "medium_count": sum(1 for r in history if r.severity == SeverityLevel.MEDIUM),
            "last_detection": max(r.timestamp for r in history) if history else None,
        }

        return stats


# グローバルインスタンス
_log_analyzer_instance = None


def get_log_analyzer() -> LogAnalyzer:
    """ログ解析器のシングルトンインスタンスを取得"""
    global _log_analyzer_instance
    if _log_analyzer_instance is None:
        _log_analyzer_instance = LogAnalyzer()
    return _log_analyzer_instance

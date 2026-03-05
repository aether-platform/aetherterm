"""LogPatternCompressor - ログパターン圧縮

ログ行の類似パターンをグルーピングし、LLMに渡す前にトークン消費を削減する。
正規化により、タイムスタンプ・PID・UUID・IP・数値等をプレースホルダーに置換。
"""

import re
import time
from dataclasses import dataclass, field

from .log_analysis_config import LogAnalysisConfig


@dataclass
class LogPattern:
    """圧縮されたログパターン"""

    normalized: str
    count: int
    samples: list[str] = field(default_factory=list)
    first_seen: float = 0.0
    last_seen: float = 0.0
    severity: str = "unknown"


@dataclass
class CompressedLogBatch:
    """圧縮されたログバッチ"""

    session_id: str
    patterns: list[LogPattern]
    total_lines: int
    unique_patterns: int
    compression_ratio: float
    time_range: tuple[float, float]


# 正規化パターン（順序が重要: より具体的なものを先に）
_NORMALIZE_RULES: list[tuple[re.Pattern, str]] = [
    # ISO 8601 タイムスタンプ (2024-01-01T12:00:00.000Z / 2024-01-01 12:00:00,000)
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.,]?\d*[Z]?"), "<TIMESTAMP>"),
    # syslog / common log タイムスタンプ (Jan  1 12:00:00)
    (
        re.compile(
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
            r"\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}"
        ),
        "<TIMESTAMP>",
    ),
    # UUID
    (
        re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"),
        "<UUID>",
    ),
    # IPv6 (簡易)
    (re.compile(r"(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}"), "<IPV6>"),
    # IPv4
    (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "<IP>"),
    # hex ハッシュ (8文字以上の16進数)
    (re.compile(r"\b[0-9a-fA-F]{8,}\b"), "<HEX>"),
    # PID / ポート番号等の括弧内数値 [12345]
    (re.compile(r"\[\d+\]"), "[<PID>]"),
    # パス中のセッションID風の長い英数字
    (re.compile(r"/[a-zA-Z0-9_-]{20,}"), "/<SESSION_ID>"),
    # 純粋な数値列 (3桁以上)
    (re.compile(r"\b\d{3,}\b"), "<NUM>"),
]

# severity 検出パターン
_SEVERITY_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:ERROR|FATAL|CRITICAL|CRIT|PANIC)\b", re.IGNORECASE), "error"),
    (re.compile(r"\b(?:WARN(?:ING)?|ALERT)\b", re.IGNORECASE), "warning"),
    (re.compile(r"\b(?:INFO|NOTICE)\b", re.IGNORECASE), "info"),
    (re.compile(r"\b(?:DEBUG|TRACE)\b", re.IGNORECASE), "debug"),
]


def _normalize_line(line: str) -> str:
    """ログ行を正規化（プレースホルダー置換）"""
    result = line
    for pattern, replacement in _NORMALIZE_RULES:
        result = pattern.sub(replacement, result)
    return result


def _detect_severity(line: str) -> str:
    """ログ行からseverityを検出"""
    for pattern, severity in _SEVERITY_PATTERNS:
        if pattern.search(line):
            return severity
    return "unknown"


class LogPatternCompressor:
    """ログパターン圧縮器"""

    def __init__(self, config: LogAnalysisConfig | None = None):
        self._max_samples = config.max_samples_per_pattern if config else 3

    def compress(self, session_id: str, entries: list[dict]) -> CompressedLogBatch:
        """ログエントリをパターン圧縮する

        Args:
            session_id: セッションID
            entries: ログエントリのリスト [{text, timestamp, source}, ...]

        Returns:
            CompressedLogBatch
        """
        pattern_map: dict[str, LogPattern] = {}
        now = time.time()
        min_ts = float("inf")
        max_ts = 0.0

        for entry in entries:
            text = entry.get("text", "")
            ts = entry.get("timestamp", now)
            if isinstance(ts, str):
                ts = now  # 文字列タイムスタンプはfallback

            min_ts = min(min_ts, ts)
            max_ts = max(max_ts, ts)

            normalized = _normalize_line(text)
            severity = _detect_severity(text)

            if normalized in pattern_map:
                pat = pattern_map[normalized]
                pat.count += 1
                pat.last_seen = ts
                if len(pat.samples) < self._max_samples:
                    pat.samples.append(text)
                # severity は最も深刻なものを保持
                if _severity_rank(severity) > _severity_rank(pat.severity):
                    pat.severity = severity
            else:
                pattern_map[normalized] = LogPattern(
                    normalized=normalized,
                    count=1,
                    samples=[text],
                    first_seen=ts,
                    last_seen=ts,
                    severity=severity,
                )

        patterns = sorted(pattern_map.values(), key=lambda p: p.count, reverse=True)
        total = len(entries)
        unique = len(patterns)

        if min_ts == float("inf"):
            min_ts = now
        if max_ts == 0.0:
            max_ts = now

        return CompressedLogBatch(
            session_id=session_id,
            patterns=patterns,
            total_lines=total,
            unique_patterns=unique,
            compression_ratio=total / unique if unique > 0 else 0.0,
            time_range=(min_ts, max_ts),
        )


def _severity_rank(severity: str) -> int:
    """severity の深刻度ランク"""
    return {"debug": 0, "unknown": 1, "info": 2, "warning": 3, "error": 4}.get(severity, 1)

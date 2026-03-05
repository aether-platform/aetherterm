#!/usr/bin/env python3
"""OODA ログパターン圧縮 + LLM自己学習パイプライン PoC

OODAループ (Observe→Orient→Decide→Act) で大量ログから未知の異常を
自動検出し、LLM分析結果をナレッジとして蓄積する自己学習パイプライン。

アーキテクチャ:
  Producer ─PUSH→ Observe ─PUSH→ Orient ─PUSH→ Decide ─PUSH→ Act
                  (Drain+LTSV)   (Vector照合)   (LLM分析)   (KB更新)
                                      ↑                        │
                                      └── KnowledgeStore ◄─────┘
                                          (自己学習ループ)

全5タスクが asyncio.gather で並行起動、ZMQ inproc PUSH/PULL で接続。

Usage:
    python ooda_log_analyzer.py                    # サンプル + Stub
    python ooda_log_analyzer.py --llm              # LLM使用
    python ooda_log_analyzer.py --file /var/log/syslog
    python ooda_log_analyzer.py --json             # JSON出力
    python ooda_log_analyzer.py --window 300       # ウィンドウ秒数
    python ooda_log_analyzer.py --threshold 0.7    # 類似度閾値
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import re
import sys
import time
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import msgpack
import zmq
import zmq.asyncio

logger = logging.getLogger(__name__)

# ========================================================================
# 正規化ルール (log_compressor_poc.py 流用、順序重要: 具体的なものを先に)
# ========================================================================

_NORMALIZE_RULES: list[tuple[re.Pattern, str]] = [
    # ISO 8601 (2024-01-01T12:00:00.000Z)
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.,]?\d*Z?"), "<TS>"),
    # syslog (Jan  1 12:00:00)
    (
        re.compile(
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
            r"\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}"
        ),
        "<TS>",
    ),
    # nginx/apache access log timestamp [24/Feb/2026:10:15:01 +0900]
    (
        re.compile(
            r"\[\d{1,2}/(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
            r"/\d{4}:\d{2}:\d{2}:\d{2}\s*[+-]?\d{4}\]"
        ),
        "[<TS>]",
    ),
    # UUID
    (
        re.compile(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
            r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
        ),
        "<UUID>",
    ),
    # IPv6 (簡易)
    (re.compile(r"(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}"), "<IPv6>"),
    # IPv4
    (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "<IP>"),
    # hex hash (8+ hex chars)
    (re.compile(r"\b[0-9a-fA-F]{8,}\b"), "<HEX>"),
    # PID [12345] / [1]
    (re.compile(r"\[\d+\]"), "[<N>]"),
    # セッションID風の長い英数字パス
    (re.compile(r"/[a-zA-Z0-9_-]{20,}"), "/<SID>"),
    # worker-N, thread-N 等の番号付きラベル
    (re.compile(r"(worker|thread|handler|task|process)-\d+"), r"\1-<N>"),
    # 3桁以上の数値
    (re.compile(r"\b\d{3,}\b"), "<N>"),
    # 2桁以下の数値 (Session 42 等)
    (re.compile(r"\b\d{1,2}\b"), "<n>"),
]

_SEVERITY_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:ERROR|FATAL|CRITICAL|CRIT|PANIC)\b", re.IGNORECASE), "error"),
    (re.compile(r"\b(?:WARN(?:ING)?|ALERT)\b", re.IGNORECASE), "warning"),
    (re.compile(r"\b(?:INFO|NOTICE)\b", re.IGNORECASE), "info"),
    (re.compile(r"\b(?:DEBUG|TRACE)\b", re.IGNORECASE), "debug"),
]

_SEVERITY_RANK = {"debug": 0, "unknown": 1, "info": 2, "warning": 3, "error": 4}


def normalize(line: str) -> str:
    result = line.strip()
    for pattern, replacement in _NORMALIZE_RULES:
        result = pattern.sub(replacement, result)
    return result


def detect_severity(line: str) -> str:
    for pattern, severity in _SEVERITY_PATTERNS:
        if pattern.search(line):
            return severity
    return "unknown"


# ========================================================================
# タイムスタンプ解析
# ========================================================================

_TS_PATTERNS = [
    # ISO 8601
    (re.compile(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})"), "%Y-%m-%dT%H:%M:%S"),
    # syslog (年はカレント年を補完)
    (
        re.compile(
            r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
            r"\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})"
        ),
        "%b %d %H:%M:%S",
    ),
    # nginx access log
    (
        re.compile(
            r"\[(\d{1,2}/(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
            r"/\d{4}:\d{2}:\d{2}:\d{2})"
        ),
        "%d/%b/%Y:%H:%M:%S",
    ),
]


def parse_timestamp(line: str) -> float | None:
    """ログ行からUNIXタイムスタンプを抽出。失敗時はNone。"""
    for pat, fmt in _TS_PATTERNS:
        m = pat.search(line)
        if m:
            ts_str = m.group(1).replace("T", " ").lstrip()
            # syslog workaround: normalize double spaces
            ts_str = re.sub(r"\s+", " ", ts_str)
            try:
                dt = datetime.strptime(ts_str, fmt.replace("T", " "))
                if dt.year == 1900:
                    dt = dt.replace(year=datetime.now().year)
                return dt.replace(tzinfo=timezone.utc).timestamp()
            except ValueError:
                continue
    return None


# ========================================================================
# DrainTree — 簡易Drainアルゴリズム
# ========================================================================


@dataclass
class DrainCluster:
    """Drainクラスタ: テンプレート + メタデータ"""
    template_tokens: list[str]
    count: int = 0
    severity: str = "unknown"
    window_counts: dict[str, int] = field(default_factory=dict)
    samples: list[str] = field(default_factory=list)
    max_samples: int = 3

    @property
    def template(self) -> str:
        return " ".join(self.template_tokens)

    def add(self, tokens: list[str], raw: str, severity: str, window_key: str) -> None:
        self.count += 1
        self.window_counts[window_key] = self.window_counts.get(window_key, 0) + 1
        if len(self.samples) < self.max_samples:
            self.samples.append(raw)
        if _SEVERITY_RANK.get(severity, 1) > _SEVERITY_RANK.get(self.severity, 1):
            self.severity = severity
        # テンプレート更新: 不一致位置を <*> に置換
        for i, (t_tok, new_tok) in enumerate(zip(self.template_tokens, tokens)):
            if t_tok != new_tok and t_tok != "<*>":
                self.template_tokens[i] = "<*>"


class DrainTree:
    """簡易Drainアルゴリズム実装

    depth 1: トークン数でバケット分類 (short/medium/long)
    depth 2: 正規化後の先頭トークンでルーティング
    depth 3: 候補クラスタとのトークン類似度比較
    """

    def __init__(self, similarity_threshold: float = 0.5):
        self._threshold = similarity_threshold
        # buckets[bucket_key][prefix_token] -> list[DrainCluster]
        self._buckets: dict[str, dict[str, list[DrainCluster]]] = {}

    @property
    def clusters(self) -> list[DrainCluster]:
        result = []
        for prefix_map in self._buckets.values():
            for cluster_list in prefix_map.values():
                result.extend(cluster_list)
        return result

    def _bucket_key(self, n_tokens: int) -> str:
        if n_tokens <= 5:
            return "short"
        elif n_tokens <= 15:
            return "medium"
        return "long"

    def add(self, raw_line: str, window_key: str) -> DrainCluster:
        """ログ行をクラスタリング。マッチするクラスタがなければ新規作成。"""
        normalized = normalize(raw_line)
        severity = detect_severity(raw_line)
        tokens = normalized.split()

        if not tokens:
            tokens = ["<EMPTY>"]

        bucket = self._bucket_key(len(tokens))
        prefix = tokens[0]

        if bucket not in self._buckets:
            self._buckets[bucket] = {}
        if prefix not in self._buckets[bucket]:
            self._buckets[bucket][prefix] = []

        candidates = self._buckets[bucket][prefix]

        best_cluster = None
        best_sim = 0.0

        for cluster in candidates:
            sim = self._token_similarity(cluster.template_tokens, tokens)
            if sim > best_sim:
                best_sim = sim
                best_cluster = cluster

        if best_cluster and best_sim >= self._threshold:
            best_cluster.add(tokens, raw_line, severity, window_key)
            return best_cluster

        # 新規クラスタ作成
        new_cluster = DrainCluster(
            template_tokens=list(tokens),
            severity=severity,
        )
        new_cluster.add(tokens, raw_line, severity, window_key)
        candidates.append(new_cluster)
        return new_cluster

    @staticmethod
    def _token_similarity(template: list[str], tokens: list[str]) -> float:
        if len(template) != len(tokens):
            return 0.0
        if not template:
            return 1.0
        matches = sum(
            1 for t, n in zip(template, tokens) if t == n or t == "<*>"
        )
        return matches / len(template)


# ========================================================================
# SimpleVectorStore — 文字3-gram + コサイン類似度 (インメモリ)
# ========================================================================


class SimpleVectorStore:
    """文字3-gramベースのベクトルストア。外部依存なし。"""

    def __init__(self):
        self._entries: list[tuple[str, Counter, str]] = []  # (template, ngram_vec, insight)

    def __len__(self) -> int:
        return len(self._entries)

    @staticmethod
    def _ngrams(text: str, n: int = 3) -> Counter:
        text = text.lower()
        return Counter(text[i : i + n] for i in range(max(0, len(text) - n + 1)))

    @staticmethod
    def _cosine(a: Counter, b: Counter) -> float:
        keys = set(a) | set(b)
        if not keys:
            return 0.0
        dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
        mag_a = math.sqrt(sum(v * v for v in a.values()))
        mag_b = math.sqrt(sum(v * v for v in b.values()))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)

    def add(self, template: str, insight: str) -> None:
        vec = self._ngrams(template)
        self._entries.append((template, vec, insight))

    def search(self, template: str, threshold: float = 0.7) -> tuple[str | None, float]:
        """テンプレートに最も類似するエントリを検索。

        Returns: (insight or None, similarity_score)
        """
        query_vec = self._ngrams(template)
        best_insight = None
        best_sim = 0.0

        for _, entry_vec, insight in self._entries:
            sim = self._cosine(query_vec, entry_vec)
            if sim > best_sim:
                best_sim = sim
                best_insight = insight

        if best_sim >= threshold:
            return best_insight, best_sim
        return None, best_sim


# ========================================================================
# スパイク検出
# ========================================================================


def detect_spikes(
    series: list[int], z_threshold: float = 2.0, ratio_threshold: float = 2.0,
    min_count: int = 3,
) -> list[int]:
    """時系列データからスパイクのあるウィンドウインデックスを返す。

    条件 (OR):
      - z-score >= z_threshold
      - 前ウィンドウ比 >= ratio_threshold (かつ count >= min_count)
    """
    if not series:
        return []

    mean = sum(series) / len(series)
    variance = sum((x - mean) ** 2 for x in series) / len(series)
    std = math.sqrt(variance) if variance > 0 else 0.0

    spikes = []
    for i, val in enumerate(series):
        if val < min_count:
            continue
        # z-score check
        if std > 0 and (val - mean) / std >= z_threshold:
            spikes.append(i)
            continue
        # ratio check (前ウィンドウ比)
        if i > 0 and series[i - 1] > 0 and val / series[i - 1] >= ratio_threshold:
            spikes.append(i)
    return spikes


# ========================================================================
# LLMクライアント (llm_analyzer.py 流用パターン)
# ========================================================================


class LLMClient(ABC):
    @abstractmethod
    async def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]: ...


class LiteLLMClient(LLMClient):
    def __init__(
        self, model: str = "gpt-4o-mini", api_key: str = "", base_url: str = "",
        timeout: int = 30,
    ):
        self._model = model
        self._api_key = api_key
        self._base_url = base_url or None
        self._timeout = timeout

    async def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        import litellm

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "timeout": self._timeout,
            "temperature": 0.1,
        }
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._base_url:
            kwargs["api_base"] = self._base_url

        response = await litellm.acompletion(**kwargs)
        content = response.choices[0].message.content or ""
        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            }
        return {"content": content, "usage": usage}


class StubLLMClient(LLMClient):
    """キーワードマッチによる決定論的insight生成。オフライン/テスト用。"""

    _RULES: list[tuple[str, str, str]] = [
        ("Failed password", "Brute-force SSH attempt from single IP", "Block IP and enforce key-only auth"),
        ("sshd", "SSH access pattern detected", "Review SSH access policy"),
        ("Connection refused", "Backend service unreachable", "Check service health and restart if needed"),
        ("pool exhausted", "Resource pool depletion — possible cascading failure", "Scale pool or investigate upstream cause"),
        ("Out of memory", "OOM kill event — memory pressure critical", "Increase memory limits or investigate leak"),
        ("Killed process", "Process terminated by kernel OOM killer", "Review process memory usage and limits"),
        ("403", "Unauthorized access attempt / scanner activity", "Review access controls and block scanner IPs"),
        ("404", "Probe for known vulnerability paths", "Ensure sensitive paths are not exposed"),
        (".env", "Sensitive file probe detected", "Block path and audit exposed files"),
        ("wp-admin", "WordPress scanner detected", "Block known scanner IPs"),
        ("Slow query", "Database performance degradation", "Optimize query or add index"),
        ("ERROR", "Application error detected", "Investigate error root cause"),
        ("WARNING", "Warning condition", "Monitor for escalation"),
    ]

    async def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
        patterns = []
        for keyword, insight, action in self._RULES:
            if keyword.lower() in user_msg.lower():
                patterns.append({
                    "template": keyword,
                    "insight": insight,
                    "action": action,
                    "confidence": 0.85,
                    "is_root_cause": keyword in ("Out of memory", "pool exhausted", "Connection refused"),
                    "correlated_with": [],
                })

        root_causes = [p for p in patterns if p.get("is_root_cause")]
        result = {
            "patterns": patterns if patterns else [{
                "template": "unknown",
                "insight": "Anomalous pattern detected",
                "action": "Investigate manually",
                "confidence": 0.5,
                "is_root_cause": False,
                "correlated_with": [],
            }],
            "root_cause_summary": root_causes[0]["insight"] if root_causes else "No clear root cause",
            "temporal_narrative": "Stub analysis — use --llm for real LLM analysis",
        }
        return {
            "content": json.dumps(result),
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }


# ========================================================================
# データモデル
# ========================================================================


@dataclass
class ObservedPattern:
    """Observe段階の出力: DrainテンプレートにLTSVメタデータ付与"""
    template: str
    count: int
    severity: str
    series: list[int]  # 各ウィンドウの発生回数
    window_keys: list[str]  # ウィンドウキーのリスト (時系列順)
    samples: list[str] = field(default_factory=list)
    insight: str = "Unknown"
    action: str = ""
    confidence: float = 0.0
    source: str = ""  # "known" / "llm" / ""
    is_root_cause: bool = False
    correlated_with: list[str] = field(default_factory=list)
    spike_windows: list[int] = field(default_factory=list)


# ========================================================================
# ZMQ アドレス
# ========================================================================

ADDR_PRODUCER_TO_OBSERVE = "inproc://producer-to-observe"
ADDR_OBSERVE_TO_ORIENT = "inproc://observe-to-orient"
ADDR_ORIENT_TO_DECIDE = "inproc://orient-to-decide"
ADDR_DECIDE_TO_ACT = "inproc://decide-to-act"


# ========================================================================
# LLMプロンプト
# ========================================================================

_SYSTEM_PROMPT = """\
You are a time-series-aware log anomaly analyzer. You receive compressed log \
patterns with per-window occurrence counts (series). Your job:

1. Correlate simultaneous spikes across different patterns.
2. Detect cascade failures (pattern A spike → pattern B spike in next window).
3. Identify severity escalation (warning → error progression).
4. Determine root cause vs symptom for each anomaly.

Respond in JSON ONLY (no markdown fences):
{
  "patterns": [
    {
      "template": "<the log template>",
      "insight": "<what this pattern means>",
      "action": "<recommended action>",
      "confidence": 0.0-1.0,
      "is_root_cause": true/false,
      "correlated_with": ["<other template snippets>"]
    }
  ],
  "root_cause_summary": "<overall root cause explanation>",
  "temporal_narrative": "<time-ordered story of what happened>"
}"""


def _build_user_prompt(patterns: list[ObservedPattern]) -> str:
    lines = ["Analyze these log patterns with time-series data:\n"]
    for i, p in enumerate(patterns, 1):
        lines.append(f"Pattern #{i}:")
        lines.append(f"  template: {p.template}")
        lines.append(f"  count: {p.count}")
        lines.append(f"  severity: {p.severity}")
        lines.append(f"  series: {p.series}")
        lines.append(f"  spike_windows: {p.spike_windows}")
        if p.samples:
            lines.append(f"  sample: {p.samples[0][:200]}")
        lines.append("")
    return "\n".join(lines)


def _parse_llm_response(content: str) -> dict:
    """LLM応答をJSONパース (markdown fence除去)"""
    cleaned = content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        start = 1 if lines[0].startswith("```") else 0
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        cleaned = "\n".join(lines[start:end])
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {}


# ========================================================================
# Task 1: Producer — ログ行をZMQ PUSHで送信
# ========================================================================


async def producer_task(
    ctx: zmq.asyncio.Context,
    lines: list[str],
    ready_event: asyncio.Event,
) -> dict:
    sock = ctx.socket(zmq.PUSH)
    sock.connect(ADDR_PRODUCER_TO_OBSERVE)

    await ready_event.wait()
    await asyncio.sleep(0.05)

    stats = {"sent": 0, "start": time.time()}

    try:
        for line in lines:
            text = line.rstrip("\n")
            if not text:
                continue
            ts = parse_timestamp(text) or time.time()
            msg = msgpack.packb({"text": text, "ts": ts})
            await sock.send(msg)
            stats["sent"] += 1

        await sock.send(msgpack.packb({"__done__": True}))
    finally:
        stats["elapsed"] = time.time() - stats["start"]
        sock.close()

    return stats


# ========================================================================
# Task 2: Observe — Drainアルゴリズム + LTSV化 + 時系列
# ========================================================================


async def observe_task(
    ctx: zmq.asyncio.Context,
    ready_event: asyncio.Event,
    window_sec: int = 300,
) -> dict:
    pull = ctx.socket(zmq.PULL)
    pull.bind(ADDR_PRODUCER_TO_OBSERVE)

    push = ctx.socket(zmq.PUSH)
    push.bind(ADDR_OBSERVE_TO_ORIENT)

    ready_event.set()

    drain = DrainTree(similarity_threshold=0.5)
    all_window_keys: set[str] = set()
    stats = {"received": 0, "clusters": 0, "start": time.time()}

    try:
        while True:
            raw = await pull.recv()
            entry = msgpack.unpackb(raw, raw=False)

            if entry.get("__done__"):
                break

            text = entry.get("text", "")
            ts = entry.get("ts", time.time())
            window_key = datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
                f"%Y-%m-%dT%H:{ts % 3600 // window_sec * (window_sec // 60):02.0f}"
            ) if window_sec < 3600 else datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M"
            )
            # 5分ウィンドウ: 10:00, 10:05, 10:10, ...
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            minute_bucket = (dt.minute // (window_sec // 60)) * (window_sec // 60)
            window_key = dt.strftime(f"%Y-%m-%dT%H:") + f"{minute_bucket:02d}"

            all_window_keys.add(window_key)
            drain.add(text, window_key)
            stats["received"] += 1

        # クラスタからObservedPatternを生成
        sorted_windows = sorted(all_window_keys)
        clusters = drain.clusters
        stats["clusters"] = len(clusters)

        observed: list[dict] = []
        for cluster in clusters:
            series = [cluster.window_counts.get(w, 0) for w in sorted_windows]
            spikes = detect_spikes(series)
            pat = ObservedPattern(
                template=cluster.template,
                count=cluster.count,
                severity=cluster.severity,
                series=series,
                window_keys=sorted_windows,
                samples=cluster.samples,
                spike_windows=spikes,
            )
            observed.append(_pattern_to_dict(pat))

        # 一括送信
        await push.send(msgpack.packb({"patterns": observed}))
        await push.send(msgpack.packb({"__done__": True}))

    finally:
        stats["elapsed"] = time.time() - stats["start"]
        pull.close()
        push.close()

    return stats


def _pattern_to_dict(p: ObservedPattern) -> dict:
    return {
        "template": p.template,
        "count": p.count,
        "severity": p.severity,
        "series": p.series,
        "window_keys": p.window_keys,
        "samples": p.samples,
        "insight": p.insight,
        "action": p.action,
        "confidence": p.confidence,
        "source": p.source,
        "is_root_cause": p.is_root_cause,
        "correlated_with": p.correlated_with,
        "spike_windows": p.spike_windows,
    }


def _dict_to_pattern(d: dict) -> ObservedPattern:
    return ObservedPattern(
        template=d["template"],
        count=d["count"],
        severity=d["severity"],
        series=d["series"],
        window_keys=d["window_keys"],
        samples=d.get("samples", []),
        insight=d.get("insight", "Unknown"),
        action=d.get("action", ""),
        confidence=d.get("confidence", 0.0),
        source=d.get("source", ""),
        is_root_cause=d.get("is_root_cause", False),
        correlated_with=d.get("correlated_with", []),
        spike_windows=d.get("spike_windows", []),
    )


# ========================================================================
# Task 3: Orient — ベクトル類似度照合
# ========================================================================


# グローバル共有ナレッジストア (Act→Orient 自己学習ループ)
_knowledge_store = SimpleVectorStore()


async def orient_task(
    ctx: zmq.asyncio.Context,
    ready_event: asyncio.Event,
    similarity_threshold: float = 0.7,
) -> dict:
    pull = ctx.socket(zmq.PULL)
    pull.connect(ADDR_OBSERVE_TO_ORIENT)

    push = ctx.socket(zmq.PUSH)
    push.bind(ADDR_ORIENT_TO_DECIDE)

    await ready_event.wait()

    stats = {"known": 0, "unknown": 0, "start": time.time()}

    try:
        while True:
            raw = await pull.recv()
            msg = msgpack.unpackb(raw, raw=False)

            if msg.get("__done__"):
                break

            patterns = msg.get("patterns", [])
            enriched = []
            for pd in patterns:
                pat = _dict_to_pattern(pd)
                insight, sim = _knowledge_store.search(pat.template, similarity_threshold)
                if insight:
                    pat.insight = insight
                    pat.source = "known"
                    pat.confidence = sim
                    stats["known"] += 1
                else:
                    stats["unknown"] += 1
                enriched.append(_pattern_to_dict(pat))

            await push.send(msgpack.packb({"patterns": enriched}))

        await push.send(msgpack.packb({"__done__": True}))

    finally:
        stats["elapsed"] = time.time() - stats["start"]
        pull.close()
        push.close()

    return stats


# ========================================================================
# Task 4: Decide — スパイク検出 + LLM分析
# ========================================================================


async def decide_task(
    ctx: zmq.asyncio.Context,
    ready_event: asyncio.Event,
    llm_client: LLMClient,
) -> dict:
    pull = ctx.socket(zmq.PULL)
    pull.connect(ADDR_ORIENT_TO_DECIDE)

    push = ctx.socket(zmq.PUSH)
    push.bind(ADDR_DECIDE_TO_ACT)

    await ready_event.wait()

    stats = {"llm_calls": 0, "patterns_analyzed": 0, "start": time.time(), "token_usage": {}}

    try:
        while True:
            raw = await pull.recv()
            msg = msgpack.unpackb(raw, raw=False)

            if msg.get("__done__"):
                break

            patterns = [_dict_to_pattern(pd) for pd in msg.get("patterns", [])]

            # LLM呼び出し対象: insight=Unknown かつ スパイクあり
            needs_llm = [p for p in patterns if p.insight == "Unknown" and p.spike_windows]
            passthrough = [p for p in patterns if p not in needs_llm]

            if needs_llm:
                stats["llm_calls"] += 1
                stats["patterns_analyzed"] += len(needs_llm)

                user_prompt = _build_user_prompt(needs_llm)
                try:
                    result = await llm_client.complete([
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ])
                    content = result["content"]
                    usage = result.get("usage", {})
                    for k, v in usage.items():
                        stats["token_usage"][k] = stats["token_usage"].get(k, 0) + v

                    parsed = _parse_llm_response(content)
                    llm_patterns = parsed.get("patterns", [])
                    root_summary = parsed.get("root_cause_summary", "")
                    narrative = parsed.get("temporal_narrative", "")

                    # LLM結果をマッチングして付与
                    for lp in llm_patterns:
                        matched = _match_llm_pattern(lp, needs_llm)
                        if matched:
                            matched.insight = lp.get("insight", matched.insight)
                            matched.action = lp.get("action", "")
                            matched.confidence = lp.get("confidence", 0.7)
                            matched.source = "llm"
                            matched.is_root_cause = lp.get("is_root_cause", False)
                            matched.correlated_with = lp.get("correlated_with", [])

                    # マッチしなかったUnknownにもデフォルトinsightを設定
                    for p in needs_llm:
                        if p.insight == "Unknown":
                            p.insight = "Anomalous spike detected"
                            p.source = "llm"
                            p.confidence = 0.3

                except Exception as e:
                    logger.warning(f"LLM call failed: {e}")
                    for p in needs_llm:
                        p.insight = f"LLM analysis failed: {e}"
                        p.source = "error"

            all_patterns = passthrough + needs_llm
            await push.send(msgpack.packb({
                "patterns": [_pattern_to_dict(p) for p in all_patterns],
            }))

        await push.send(msgpack.packb({"__done__": True}))

    finally:
        stats["elapsed"] = time.time() - stats["start"]
        pull.close()
        push.close()

    return stats


def _match_llm_pattern(
    llm_pat: dict, candidates: list[ObservedPattern],
) -> ObservedPattern | None:
    """LLM応答のパターンを候補リストからベストマッチで返す"""
    llm_template = llm_pat.get("template", "").lower()
    if not llm_template:
        return candidates[0] if candidates else None

    best = None
    best_score = 0.0
    for c in candidates:
        # 部分文字列マッチ or 3-gram類似度
        ct = c.template.lower()
        if llm_template in ct or ct in llm_template:
            return c
        # 簡易スコア
        common = sum(1 for ch in llm_template if ch in ct)
        score = common / max(len(llm_template), 1)
        if score > best_score:
            best_score = score
            best = c

    return best if best_score > 0.3 else (candidates[0] if candidates else None)


# ========================================================================
# Task 5: Act — ナレッジ書き戻し + 出力
# ========================================================================


async def act_task(
    ctx: zmq.asyncio.Context,
    ready_event: asyncio.Event,
    output_json: bool = False,
) -> dict:
    pull = ctx.socket(zmq.PULL)
    pull.connect(ADDR_DECIDE_TO_ACT)

    await ready_event.wait()

    all_patterns: list[ObservedPattern] = []
    kb_added = 0
    stats = {"start": time.time()}

    try:
        while True:
            raw = await pull.recv()
            msg = msgpack.unpackb(raw, raw=False)

            if msg.get("__done__"):
                break

            patterns = [_dict_to_pattern(pd) for pd in msg.get("patterns", [])]

            for pat in patterns:
                # ナレッジ書き戻し: confidence >= 0.5 のLLMinsightをKBに追加
                if pat.source == "llm" and pat.confidence >= 0.5 and pat.insight != "Unknown":
                    _knowledge_store.add(pat.template, pat.insight)
                    kb_added += 1
                all_patterns.append(pat)

    finally:
        stats["elapsed"] = time.time() - stats["start"]
        stats["total_patterns"] = len(all_patterns)
        stats["kb_added"] = kb_added
        stats["kb_total"] = len(_knowledge_store)
        pull.close()

    # 出力
    if output_json:
        _print_json_output(all_patterns)
    else:
        _print_ltsv_output(all_patterns)

    return {**stats, "patterns": all_patterns}


# ========================================================================
# 表示
# ========================================================================


def _format_ltsv(pat: ObservedPattern) -> str:
    """LTSV形式に変換"""
    parts = [
        f"template:{pat.template}",
        f"count:{pat.count}",
        f"severity:{pat.severity}",
        f"series:{json.dumps(pat.series)}",
    ]
    if pat.window_keys:
        parts.append(f"window:{pat.window_keys[0]}")
    parts.append(f"insight:{pat.insight}")
    if pat.action:
        parts.append(f"action:{pat.action}")
    if pat.confidence > 0:
        parts.append(f"confidence:{pat.confidence:.2f}")
    if pat.source:
        parts.append(f"source:{pat.source}")
    if pat.is_root_cause:
        parts.append("root_cause:true")
    if pat.correlated_with:
        parts.append(f"correlated_with:{','.join(pat.correlated_with)}")
    if pat.spike_windows:
        parts.append(f"spike_windows:{json.dumps(pat.spike_windows)}")
    return "\t".join(parts)


def _print_ltsv_output(patterns: list[ObservedPattern]) -> None:
    print(f"\n{'=' * 80}")
    print("  OODA Log Analysis Results (LTSV)")
    print(f"{'=' * 80}")

    # severity順でソート
    sorted_pats = sorted(
        patterns,
        key=lambda p: (-_SEVERITY_RANK.get(p.severity, 1), -p.count),
    )

    for pat in sorted_pats:
        # ヘッダー行
        spike_mark = " ** SPIKE **" if pat.spike_windows else ""
        root_mark = " [ROOT CAUSE]" if pat.is_root_cause else ""
        source_mark = f" ({pat.source})" if pat.source else ""

        severity_icon = {
            "error": "!!",
            "warning": "! ",
            "info": "  ",
            "debug": "  ",
        }.get(pat.severity, "  ")

        print(f"\n  {severity_icon} [{pat.severity:>7s}] x{pat.count:<4d}{spike_mark}{root_mark}{source_mark}")
        print(f"     template: {pat.template}")
        print(f"     series:   {pat.series}")
        if pat.insight != "Unknown":
            print(f"     insight:  {pat.insight}")
        if pat.action:
            print(f"     action:   {pat.action}")
        if pat.confidence > 0:
            print(f"     confidence: {pat.confidence:.2f}")

    # LTSV生セクション
    print(f"\n{'-' * 80}")
    print("  Raw LTSV:")
    print(f"{'-' * 80}")
    for pat in sorted_pats:
        print(_format_ltsv(pat))


def _print_json_output(patterns: list[ObservedPattern]) -> None:
    output = {
        "patterns": [
            {
                "template": p.template,
                "count": p.count,
                "severity": p.severity,
                "series": p.series,
                "window_keys": p.window_keys,
                "insight": p.insight,
                "action": p.action,
                "confidence": p.confidence,
                "source": p.source,
                "is_root_cause": p.is_root_cause,
                "correlated_with": p.correlated_with,
                "spike_windows": p.spike_windows,
                "sample": p.samples[0] if p.samples else "",
            }
            for p in patterns
        ],
        "summary": {
            "total_patterns": len(patterns),
            "by_severity": {},
            "by_source": {},
            "spike_count": sum(1 for p in patterns if p.spike_windows),
            "root_causes": [p.template for p in patterns if p.is_root_cause],
        },
    }
    # severity/source集計
    for p in patterns:
        output["summary"]["by_severity"][p.severity] = (
            output["summary"]["by_severity"].get(p.severity, 0) + 1
        )
        src = p.source or "none"
        output["summary"]["by_source"][src] = (
            output["summary"]["by_source"].get(src, 0) + 1
        )
    print(json.dumps(output, ensure_ascii=False, indent=2))


# ========================================================================
# サンプルログ — 複数5分ウィンドウにまたがるシナリオ
# ========================================================================


def generate_sample_logs() -> list[str]:
    """リアルなマルチウィンドウ攻撃/障害シナリオを生成"""
    logs = []

    # Window 10:00-10:05 — 平常運用
    for i in range(3):
        logs.append(f"2026-02-24T10:0{i}:00.000Z INFO  [main] Application started on port 808{i}")
    logs.append("2026-02-24T10:01:00.000Z INFO  [worker-1] Processing request abc12345-1234-5678-9012-abcdef123456")
    logs.append("2026-02-24T10:02:00.000Z INFO  [worker-2] Health check passed")
    logs.append("Feb 24 10:03:00 web-01 systemd[1]: Started Session 42 of user deploy.")
    logs.append("Feb 24 10:04:00 web-01 systemd[1]: Started Session 43 of user deploy.")

    # Window 10:05-10:10 — 初期兆候
    logs.append("2026-02-24T10:05:01.000Z WARNING [worker-1] Slow query detected: 2345ms for SELECT * FROM users")
    logs.append("2026-02-24T10:06:01.000Z WARNING [worker-2] Slow query detected: 3456ms for SELECT * FROM orders")
    logs.append("Feb 24 10:07:00 web-01 sshd[12348]: Failed password for root from 10.0.0.50 port 44100 ssh2")
    logs.append("Feb 24 10:08:00 web-01 sshd[12349]: Failed password for root from 10.0.0.50 port 44101 ssh2")

    # Window 10:10-10:15 — SSH brute force スパイク + DB接続エラー開始
    for i in range(15):
        logs.append(f"Feb 24 10:1{i % 5}:0{i:01d} web-01 sshd[{12400+i}]: Failed password for root from 10.0.0.50 port {44200+i} ssh2")
    logs.append("2026-02-24T10:10:30.000Z ERROR [worker-1] Connection refused to 10.0.1.50:5432")
    logs.append("2026-02-24T10:11:30.000Z ERROR [worker-2] Connection refused to 10.0.1.50:5432")
    # nginx scanner
    logs.append('10.0.0.50 - - [24/Feb/2026:10:12:00 +0900] "GET /.env HTTP/1.1" 404 0')
    logs.append('10.0.0.50 - - [24/Feb/2026:10:12:01 +0900] "GET /wp-admin HTTP/1.1" 404 0')
    logs.append('10.0.0.50 - - [24/Feb/2026:10:13:00 +0900] "GET /admin/config HTTP/1.1" 403 89')

    # Window 10:15-10:20 — DB接続エラースパイク → アプリエラー連鎖
    for i in range(8):
        logs.append(f"2026-02-24T10:1{5+i//4}:{i*7:02d}.000Z ERROR [worker-{1+i%2}] Connection refused to 10.0.1.5{i%3}:5432")
    logs.append("2026-02-24T10:16:00.000Z CRITICAL [health] Database pool exhausted")
    logs.append("2026-02-24T10:17:00.000Z ERROR [api] Request timeout: GET /api/v1/users after 30000ms")
    logs.append("2026-02-24T10:18:00.000Z ERROR [api] Request timeout: POST /api/v1/sessions after 30000ms")

    # Window 10:20-10:25 — OOM kill 突発
    logs.append("Feb 24 10:20:00 web-01 kernel: [  123.456789] Out of memory: Killed process 9876 (java) total-vm:4096000kB")
    logs.append("Feb 24 10:21:00 web-01 kernel: [  124.567890] Out of memory: Killed process 9877 (java) total-vm:4096000kB")
    logs.append("Feb 24 10:22:00 web-01 kernel: [  125.678901] Out of memory: Killed process 9878 (python3) total-vm:2048000kB")
    # 正常ログも混在
    logs.append("2026-02-24T10:23:00.000Z INFO  [worker-1] Service restarted successfully")
    logs.append("Feb 24 10:24:00 web-01 sshd[12500]: Accepted publickey for deploy from 192.168.1.100 port 54321 ssh2")

    return logs


# ========================================================================
# パイプライン起動
# ========================================================================


async def run_pipeline(
    lines: list[str],
    use_llm: bool = False,
    output_json: bool = False,
    window_sec: int = 300,
    similarity_threshold: float = 0.7,
) -> None:
    ctx = zmq.asyncio.Context()
    ready = asyncio.Event()

    # LLMクライアント選択
    if use_llm:
        api_key = os.environ.get("LOG_LLM_API_KEY", "")
        model = os.environ.get("LOG_LLM_MODEL", "gpt-4o-mini")
        base_url = os.environ.get("LOG_LLM_BASE_URL", "")
        llm_client: LLMClient = LiteLLMClient(
            model=model, api_key=api_key, base_url=base_url,
        )
    else:
        llm_client = StubLLMClient()

    if not output_json:
        mode = "LiteLLM" if use_llm else "Stub"
        print(f"OODA Log Analyzer — {len(lines)} lines, window={window_sec}s, "
              f"threshold={similarity_threshold}, llm={mode}")
        print(f"Pipeline: Producer →PUSH→ Observe →PUSH→ Orient →PUSH→ Decide →PUSH→ Act")
        print(f"{'─' * 80}")

    pipeline_start = time.time()

    try:
        results = await asyncio.gather(
            producer_task(ctx, lines, ready),
            observe_task(ctx, ready, window_sec),
            orient_task(ctx, ready, similarity_threshold),
            decide_task(ctx, ready, llm_client),
            act_task(ctx, ready, output_json),
        )

        producer_stats, observe_stats, orient_stats, decide_stats, act_stats = results

        if not output_json:
            elapsed = time.time() - pipeline_start
            total_lines = producer_stats["sent"]
            total_patterns = act_stats.get("total_patterns", 0)
            compression = total_lines / total_patterns if total_patterns > 0 else 0

            print(f"\n{'#' * 80}")
            print(f"  OODA Pipeline Summary")
            print(f"{'#' * 80}")
            print(f"  Producer : {producer_stats['sent']} lines sent "
                  f"in {producer_stats['elapsed']:.3f}s")
            print(f"  Observe  : {observe_stats['received']} lines → "
                  f"{observe_stats['clusters']} Drain clusters "
                  f"in {observe_stats['elapsed']:.3f}s")
            print(f"  Orient   : {orient_stats['known']} known, "
                  f"{orient_stats['unknown']} unknown "
                  f"in {orient_stats['elapsed']:.3f}s")
            print(f"  Decide   : {decide_stats['llm_calls']} LLM calls, "
                  f"{decide_stats['patterns_analyzed']} patterns analyzed "
                  f"in {decide_stats['elapsed']:.3f}s")
            if decide_stats.get("token_usage"):
                usage = decide_stats["token_usage"]
                print(f"           : tokens: {usage}")
            print(f"  Act      : {act_stats['kb_added']} insights → KB "
                  f"(total KB: {act_stats['kb_total']}) "
                  f"in {act_stats['elapsed']:.3f}s")
            print(f"  ─────────────────────────────────────────")
            print(f"  Overall  : {total_lines} lines → {total_patterns} patterns "
                  f"({compression:.1f}x compression)")
            print(f"  Pipeline : {elapsed:.3f}s total")
            print(f"{'#' * 80}")

    finally:
        ctx.term()


# ========================================================================
# メイン
# ========================================================================


def main():
    parser = argparse.ArgumentParser(
        description="OODA Log Pattern Compressor + LLM Self-Learning Pipeline PoC"
    )
    parser.add_argument("--file", "-f", help="ログファイルパス")
    parser.add_argument("--stdin", action="store_true", help="stdinから読み込み")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    parser.add_argument("--llm", action="store_true",
                        help="LLM使用 (要 LOG_LLM_API_KEY)")
    parser.add_argument("--window", type=int, default=300,
                        help="時系列ウィンドウ秒数 (default: 300)")
    parser.add_argument("--threshold", type=float, default=0.7,
                        help="Orient類似度閾値 (default: 0.7)")
    args = parser.parse_args()

    if args.stdin:
        lines = sys.stdin.readlines()
    elif args.file:
        with open(args.file) as f:
            lines = f.readlines()
    else:
        lines = generate_sample_logs()

    logging.basicConfig(
        level=logging.DEBUG if os.environ.get("DEBUG") else logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    asyncio.run(run_pipeline(
        lines=lines,
        use_llm=args.llm,
        output_json=args.json,
        window_sec=args.window,
        similarity_threshold=args.threshold,
    ))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""ログパターン圧縮 PoC — asyncio + ZMQ パイプライン

3つの非同期タスクがZMQ経由でデータを受け渡す自己完結デモ:

  Producer (PUSH) ──→ Buffer (PULL→PUSH) ──→ Compressor (PULL)
  ログ行を送信        バッファリング+フラッシュ   正規化+パターン圧縮

Usage:
    python log_compressor_poc.py                # サンプルデータで実行
    python log_compressor_poc.py --file /var/log/syslog
    python log_compressor_poc.py --json         # JSON出力
    python log_compressor_poc.py --rate 100     # 100行/秒で送信
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import signal
import sys
import time
from dataclasses import dataclass, field

import msgpack
import zmq
import zmq.asyncio


# ========================================================================
# 正規化ルール（順序重要: 具体的なものを先に）
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
    # 2桁の数値（Session 42 等）
    (re.compile(r"\b\d{1,2}\b"), "<n>"),
]

_SEVERITY_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:ERROR|FATAL|CRITICAL|CRIT|PANIC)\b", re.IGNORECASE), "error"),
    (re.compile(r"\b(?:WARN(?:ING)?|ALERT)\b", re.IGNORECASE), "warning"),
    (re.compile(r"\b(?:INFO|NOTICE)\b", re.IGNORECASE), "info"),
    (re.compile(r"\b(?:DEBUG|TRACE)\b", re.IGNORECASE), "debug"),
]

_SEVERITY_RANK = {"debug": 0, "unknown": 1, "info": 2, "warning": 3, "error": 4}


# ========================================================================
# データモデル
# ========================================================================


@dataclass
class LogPattern:
    normalized: str
    count: int
    samples: list[str] = field(default_factory=list)
    first_seen: float = 0.0
    last_seen: float = 0.0
    severity: str = "unknown"


@dataclass
class CompressedResult:
    patterns: list[LogPattern]
    total_lines: int
    unique_patterns: int
    compression_ratio: float
    severity_counts: dict[str, int] = field(default_factory=dict)


# ========================================================================
# コア圧縮ロジック
# ========================================================================


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


def compress_batch(entries: list[dict], max_samples: int = 3) -> CompressedResult:
    """msgpackデシリアライズ済みエントリを圧縮"""
    pattern_map: dict[str, LogPattern] = {}
    severity_counts: dict[str, int] = {}

    for entry in entries:
        text: str = entry.get("text", "")
        ts: float = entry.get("ts", time.time())
        if not text:
            continue

        normalized = normalize(text)
        severity = detect_severity(text)
        severity_counts[severity] = severity_counts.get(severity, 0) + 1

        if normalized in pattern_map:
            pat = pattern_map[normalized]
            pat.count += 1
            pat.last_seen = ts
            if len(pat.samples) < max_samples:
                pat.samples.append(text)
            if _SEVERITY_RANK.get(severity, 1) > _SEVERITY_RANK.get(pat.severity, 1):
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
    total = sum(p.count for p in patterns)
    unique = len(patterns)

    return CompressedResult(
        patterns=patterns,
        total_lines=total,
        unique_patterns=unique,
        compression_ratio=total / unique if unique > 0 else 0.0,
        severity_counts=severity_counts,
    )


# ========================================================================
# ZMQ アドレス
# ========================================================================

ADDR_PRODUCER_TO_BUFFER = "inproc://producer-to-buffer"
ADDR_BUFFER_TO_COMPRESSOR = "inproc://buffer-to-compressor"


# ========================================================================
# Task 1: Producer — ログ行をZMQ PUSHで送信
# ========================================================================


async def producer_task(
    ctx: zmq.asyncio.Context,
    lines: list[str],
    rate: float,
    ready_event: asyncio.Event,
) -> dict:
    """ログ行をPUSHソケットで1行ずつ送信"""
    sock = ctx.socket(zmq.PUSH)
    sock.connect(ADDR_PRODUCER_TO_BUFFER)

    # Buffer側がbindするのを待つ
    await ready_event.wait()
    await asyncio.sleep(0.05)  # inproc接続安定待ち

    stats = {"sent": 0, "start": time.time()}
    delay = 1.0 / rate if rate > 0 else 0

    try:
        for line in lines:
            msg = msgpack.packb({"text": line.rstrip("\n"), "ts": time.time()})
            await sock.send(msg)
            stats["sent"] += 1
            if delay > 0:
                await asyncio.sleep(delay)

        # 終了シグナル
        await sock.send(msgpack.packb({"__done__": True}))
    finally:
        stats["elapsed"] = time.time() - stats["start"]
        sock.close()

    return stats


# ========================================================================
# Task 2: Buffer — バッファリング + 閾値フラッシュ
# ========================================================================


async def buffer_task(
    ctx: zmq.asyncio.Context,
    max_lines: int,
    max_interval_sec: float,
    ready_event: asyncio.Event,
) -> dict:
    """PULLで受信 → バッファ蓄積 → 閾値到達でPUSH送信"""
    pull = ctx.socket(zmq.PULL)
    pull.bind(ADDR_PRODUCER_TO_BUFFER)

    push = ctx.socket(zmq.PUSH)
    push.bind(ADDR_BUFFER_TO_COMPRESSOR)

    ready_event.set()

    buffer: list[dict] = []
    last_flush = time.time()
    stats = {"received": 0, "flushes": 0, "start": time.time()}
    done = False

    try:
        while not done:
            # タイムアウト付きで受信（時間ベースフラッシュのため）
            try:
                raw = await asyncio.wait_for(pull.recv(), timeout=max_interval_sec / 4)
                entry = msgpack.unpackb(raw, raw=False)

                if entry.get("__done__"):
                    done = True
                else:
                    buffer.append(entry)
                    stats["received"] += 1
            except asyncio.TimeoutError:
                pass

            # フラッシュ判定
            now = time.time()
            count_trigger = len(buffer) >= max_lines
            time_trigger = (now - last_flush) >= max_interval_sec and len(buffer) > 0
            final_flush = done and len(buffer) > 0

            if count_trigger or time_trigger or final_flush:
                batch = msgpack.packb({"entries": buffer, "flush_reason": (
                    "count" if count_trigger else "time" if time_trigger else "final"
                )})
                await push.send(batch)
                stats["flushes"] += 1
                buffer = []
                last_flush = now

        # 終了シグナル
        await push.send(msgpack.packb({"__done__": True}))
    finally:
        stats["elapsed"] = time.time() - stats["start"]
        pull.close()
        push.close()

    return stats


# ========================================================================
# Task 3: Compressor — パターン圧縮 + 結果出力
# ========================================================================


async def compressor_task(
    ctx: zmq.asyncio.Context,
    ready_event: asyncio.Event,
    output_json: bool = False,
) -> list[CompressedResult]:
    """PULLでバッチ受信 → パターン圧縮 → 結果表示"""
    sock = ctx.socket(zmq.PULL)
    sock.connect(ADDR_BUFFER_TO_COMPRESSOR)

    await ready_event.wait()

    results: list[CompressedResult] = []
    batch_num = 0

    try:
        while True:
            raw = await sock.recv()
            msg = msgpack.unpackb(raw, raw=False)

            if msg.get("__done__"):
                break

            batch_num += 1
            entries = msg.get("entries", [])
            flush_reason = msg.get("flush_reason", "?")

            result = compress_batch(entries)
            results.append(result)

            if output_json:
                _print_result_json(batch_num, flush_reason, result)
            else:
                _print_result_table(batch_num, flush_reason, result)
    finally:
        sock.close()

    return results


# ========================================================================
# 表示
# ========================================================================


def _print_result_table(batch_num: int, reason: str, r: CompressedResult) -> None:
    print(f"\n{'=' * 72}")
    print(f"  Batch #{batch_num}  (flush: {reason})")
    print(f"  {r.total_lines} lines → {r.unique_patterns} patterns  "
          f"({r.compression_ratio:.1f}x compression)")
    print(f"  Severity: {json.dumps(r.severity_counts)}")
    print(f"{'-' * 72}")

    for i, pat in enumerate(r.patterns, 1):
        mark = {"error": "!!", "warning": "! "}.get(pat.severity, "  ")
        print(f"  {mark} #{i:<3d} x{pat.count:<4d} [{pat.severity:>7s}]  {pat.normalized}")
        if pat.samples:
            print(f"       sample: {pat.samples[0][:100]}")

    # トークン推定
    raw_chars = sum(len(s) for p in r.patterns for s in p.samples)
    prompt_chars = sum(len(p.normalized) + 30 for p in r.patterns)  # header overhead
    if raw_chars > 0:
        saving = (1 - prompt_chars / raw_chars) * 100
        print(f"\n  Token est: {raw_chars:,} raw → {prompt_chars:,} normalized ({saving:+.0f}%)")
    print(f"{'=' * 72}")


def _print_result_json(batch_num: int, reason: str, r: CompressedResult) -> None:
    output = {
        "batch": batch_num,
        "flush_reason": reason,
        "total_lines": r.total_lines,
        "unique_patterns": r.unique_patterns,
        "compression_ratio": round(r.compression_ratio, 2),
        "severity_counts": r.severity_counts,
        "patterns": [
            {
                "normalized": p.normalized,
                "count": p.count,
                "severity": p.severity,
                "sample": p.samples[0] if p.samples else "",
            }
            for p in r.patterns
        ],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


# ========================================================================
# サンプルログ
# ========================================================================


def generate_sample_logs() -> list[str]:
    return [
        # sshd: 成功ログイン (3件 → 1パターン)
        "Feb 24 10:15:01 web-01 sshd[12345]: Accepted publickey for deploy from 192.168.1.100 port 54321 ssh2",
        "Feb 24 10:15:01 web-01 sshd[12346]: Accepted publickey for deploy from 192.168.1.101 port 54322 ssh2",
        "Feb 24 10:15:02 web-01 sshd[12347]: Accepted publickey for deploy from 192.168.1.102 port 54323 ssh2",
        # sshd: 失敗ログイン (5件 → 1パターン)
        "Feb 24 10:15:03 web-01 sshd[12348]: Failed password for root from 10.0.0.50 port 44100 ssh2",
        "Feb 24 10:15:04 web-01 sshd[12349]: Failed password for root from 10.0.0.50 port 44101 ssh2",
        "Feb 24 10:15:05 web-01 sshd[12350]: Failed password for root from 10.0.0.50 port 44102 ssh2",
        "Feb 24 10:15:06 web-01 sshd[12351]: Failed password for root from 10.0.0.50 port 44103 ssh2",
        "Feb 24 10:15:07 web-01 sshd[12352]: Failed password for root from 10.0.0.50 port 44104 ssh2",
        # アプリ: INFO (5件 → 2パターン)
        "2026-02-24T10:15:01.123Z INFO  [main] Application started on port 8080",
        "2026-02-24T10:15:02.456Z INFO  [main] Application started on port 8081",
        "2026-02-24T10:15:03.789Z INFO  [worker-1] Processing request abc12345-1234-5678-9012-abcdef123456",
        "2026-02-24T10:15:04.012Z INFO  [worker-2] Processing request def67890-1234-5678-9012-abcdef654321",
        "2026-02-24T10:15:05.345Z INFO  [worker-1] Processing request 11111111-2222-3333-4444-555555555555",
        # アプリ: WARNING (2件 → 1パターン)
        "2026-02-24T10:15:06.678Z WARNING [worker-2] Slow query detected: 2345ms for SELECT * FROM users",
        "2026-02-24T10:15:07.901Z WARNING [worker-1] Slow query detected: 3456ms for SELECT * FROM orders",
        # アプリ: ERROR (3件 → 1パターン)
        "2026-02-24T10:15:08.234Z ERROR [worker-2] Connection refused to 10.0.1.50:5432",
        "2026-02-24T10:15:09.567Z ERROR [worker-1] Connection refused to 10.0.1.50:5432",
        "2026-02-24T10:15:10.890Z ERROR [worker-2] Connection refused to 10.0.1.51:5432",
        # アプリ: CRITICAL (1件)
        "2026-02-24T10:15:11.123Z CRITICAL [health] Database pool exhausted",
        # nginx access log (7件 → いくつかのパターン)
        '192.168.1.100 - deploy [24/Feb/2026:10:15:01 +0900] "GET /api/v1/users HTTP/1.1" 200 1234',
        '192.168.1.101 - deploy [24/Feb/2026:10:15:02 +0900] "GET /api/v1/users HTTP/1.1" 200 1235',
        '192.168.1.102 - admin [24/Feb/2026:10:15:03 +0900] "POST /api/v1/sessions HTTP/1.1" 201 567',
        '10.0.0.50 - - [24/Feb/2026:10:15:04 +0900] "GET /admin/config HTTP/1.1" 403 89',
        '10.0.0.50 - - [24/Feb/2026:10:15:05 +0900] "GET /admin/users HTTP/1.1" 403 89',
        '10.0.0.50 - - [24/Feb/2026:10:15:06 +0900] "GET /.env HTTP/1.1" 404 0',
        '10.0.0.50 - - [24/Feb/2026:10:15:07 +0900] "GET /wp-admin HTTP/1.1" 404 0',
        # kernel OOM (2件 → 1パターン)
        "Feb 24 10:15:01 web-01 kernel: [  123.456789] Out of memory: Killed process 9876 (java) total-vm:4096000kB",
        "Feb 24 10:15:02 web-01 kernel: [  124.567890] Out of memory: Killed process 9877 (java) total-vm:4096000kB",
        # systemd (3件 → 1パターン)
        "Feb 24 10:15:03 web-01 systemd[1]: Started Session 42 of user deploy.",
        "Feb 24 10:15:04 web-01 systemd[1]: Started Session 43 of user deploy.",
        "Feb 24 10:15:05 web-01 systemd[1]: Started Session 44 of user admin.",
    ]


# ========================================================================
# パイプライン起動
# ========================================================================


async def run_pipeline(
    lines: list[str],
    rate: float = 0,
    buffer_max_lines: int = 50,
    buffer_interval: float = 5.0,
    output_json: bool = False,
) -> None:
    ctx = zmq.asyncio.Context()
    ready = asyncio.Event()

    if not output_json:
        print(f"Pipeline: {len(lines)} lines, "
              f"buffer={buffer_max_lines} lines / {buffer_interval}s, "
              f"rate={'unlimited' if rate <= 0 else f'{rate}/s'}")
        print(f"ZMQ: Producer →(PUSH/PULL)→ Buffer →(PUSH/PULL)→ Compressor")

    try:
        # 3タスクを並行起動
        producer_coro = producer_task(ctx, lines, rate, ready)
        buffer_coro = buffer_task(ctx, buffer_max_lines, buffer_interval, ready)
        compressor_coro = compressor_task(ctx, ready, output_json)

        producer_result, buffer_result, compress_results = await asyncio.gather(
            producer_coro, buffer_coro, compressor_coro
        )

        # サマリー
        if not output_json:
            print(f"\n{'#' * 72}")
            print(f"  Pipeline Summary")
            print(f"{'#' * 72}")
            print(f"  Producer : {producer_result['sent']} lines sent "
                  f"in {producer_result['elapsed']:.2f}s")
            print(f"  Buffer   : {buffer_result['received']} received, "
                  f"{buffer_result['flushes']} flushes "
                  f"in {buffer_result['elapsed']:.2f}s")
            print(f"  Compressor: {len(compress_results)} batches processed")

            total_lines = sum(r.total_lines for r in compress_results)
            total_patterns = sum(r.unique_patterns for r in compress_results)
            if total_patterns > 0:
                print(f"  Overall  : {total_lines} lines → {total_patterns} patterns "
                      f"({total_lines / total_patterns:.1f}x)")
            print(f"{'#' * 72}")

    finally:
        ctx.term()


# ========================================================================
# メイン
# ========================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Log Pattern Compressor PoC (asyncio + ZMQ pipeline)"
    )
    parser.add_argument("--file", "-f", help="ログファイルパス")
    parser.add_argument("--stdin", action="store_true", help="stdinからログを読み込み")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    parser.add_argument("--rate", type=float, default=0,
                        help="送信レート (行/秒, 0=unlimited)")
    parser.add_argument("--buffer-lines", type=int, default=50,
                        help="バッファの件数閾値 (default: 50)")
    parser.add_argument("--buffer-interval", type=float, default=5.0,
                        help="バッファの時間閾値 秒 (default: 5.0)")
    args = parser.parse_args()

    if args.stdin:
        lines = sys.stdin.readlines()
    elif args.file:
        with open(args.file) as f:
            lines = f.readlines()
    else:
        lines = generate_sample_logs()

    asyncio.run(run_pipeline(
        lines=lines,
        rate=args.rate,
        buffer_max_lines=args.buffer_lines,
        buffer_interval=args.buffer_interval,
        output_json=args.json,
    ))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""LLMストリーム分析: ユニットテスト

テスト項目:
  1. ANSIストリッパー (各種エスケープシーケンス)
  2. デバウンスバッファ (サイズ閾値、タイマー)
  3. LLMStreamAnalyzer (モック、ZMQ統合)
"""

import asyncio
import sys
import time

from ansi_stripper import strip_ansi
from stream_analyzer import (
    AnalysisResult,
    AnalyzerConfig,
    DebounceBuffer,
    LLMStreamAnalyzer,
)

# ---- テストユーティリティ ----


def result(name: str, passed: bool, detail: str = "") -> None:
    mark = "\033[32mPASS\033[0m" if passed else "\033[31mFAIL\033[0m"
    suffix = f" ({detail})" if detail else ""
    print(f"  [{mark}] {name}{suffix}")


# ==== ANSIストリッパー テスト ====


async def test_strip_ansi_basic() -> bool:
    """ANSIストリッパー: 基本SGRシーケンス除去"""
    # 赤色テキスト: ESC[31mHelloESC[0m
    data = b"\x1b[31mHello\x1b[0m World"
    text = strip_ansi(data)
    return text == "Hello World"


async def test_strip_ansi_csi() -> bool:
    """ANSIストリッパー: CSIシーケンス (カーソル移動等)"""
    # カーソル移動 + テキスト + 画面クリア
    data = b"\x1b[2J\x1b[H\x1b[1;32muser@host\x1b[0m:\x1b[1;34m~/dir\x1b[0m$ ls"
    text = strip_ansi(data)
    return text == "user@host:~/dir$ ls"


async def test_strip_ansi_osc() -> bool:
    """ANSIストリッパー: OSCシーケンス (タイトル設定等)"""
    # OSC title: ESC]0;title BEL
    data = b"\x1b]0;Terminal Title\x07Some text"
    text = strip_ansi(data)
    return text == "Some text"


async def test_strip_ansi_preserves_newlines() -> bool:
    """ANSIストリッパー: 改行・タブは保持"""
    data = b"\x1b[32mLine1\x1b[0m\nLine2\tTabbed\r\n"
    text = strip_ansi(data)
    return text == "Line1\nLine2\tTabbed\r\n"


async def test_strip_ansi_empty() -> bool:
    """ANSIストリッパー: 空入力"""
    return strip_ansi(b"") == ""


async def test_strip_ansi_plain_text() -> bool:
    """ANSIストリッパー: プレーンテキスト (エスケープなし)"""
    data = b"Hello World 123"
    return strip_ansi(data) == "Hello World 123"


async def test_strip_ansi_256color() -> bool:
    """ANSIストリッパー: 256色・24bitカラー"""
    # 256色: ESC[38;5;196m  24bitカラー: ESC[38;2;255;0;0m
    data = b"\x1b[38;5;196mRed256\x1b[0m \x1b[38;2;255;0;0mRedRGB\x1b[0m"
    text = strip_ansi(data)
    return text == "Red256 RedRGB"


async def test_strip_ansi_control_chars() -> bool:
    """ANSIストリッパー: 制御文字除去 (BEL等)"""
    data = b"\x07Bell\x08Backspace"
    text = strip_ansi(data)
    return text == "BellBackspace"


# ==== デバウンスバッファ テスト ====


async def test_debounce_size_threshold() -> bool:
    """デバウンスバッファ: サイズ閾値でフラッシュ"""
    buf = DebounceBuffer(interval=10.0, max_bytes=20)  # 長いinterval

    # 小さなデータ → フラッシュされない
    r1 = await buf.add("Hello")  # 5 bytes
    if r1 is not None:
        return False

    # 閾値超えるデータ → フラッシュ
    r2 = await buf.add("A" * 20)  # 20 bytes → total 25 >= 20
    if r2 is None:
        return False

    return r2 == "Hello" + "A" * 20


async def test_debounce_timer_flush() -> bool:
    """デバウンスバッファ: タイマーでフラッシュ"""
    buf = DebounceBuffer(interval=0.1, max_bytes=99999)

    # データ追加
    await buf.add("Test data")

    # タイマー待ち
    flushed = await asyncio.wait_for(buf.wait_flush(), timeout=2.0)

    return flushed == "Test data"


async def test_debounce_accumulation() -> bool:
    """デバウンスバッファ: 複数データの蓄積"""
    buf = DebounceBuffer(interval=0.15, max_bytes=99999)

    # 短い間隔でデータ追加
    await buf.add("A")
    await asyncio.sleep(0.05)
    await buf.add("B")
    await asyncio.sleep(0.05)
    await buf.add("C")

    # タイマー満了を待つ
    flushed = await asyncio.wait_for(buf.wait_flush(), timeout=2.0)

    return flushed == "ABC"


async def test_debounce_empty_buffer() -> bool:
    """デバウンスバッファ: 空バッファでのフラッシュ"""
    buf = DebounceBuffer(interval=10.0, max_bytes=10)

    # 空の状態でサイズチェック
    return buf.buffered_size == 0


# ==== LLMStreamAnalyzer テスト (モック) ====


async def test_analyzer_mock_normal() -> bool:
    """LLMStreamAnalyzer: モック - 通常出力"""
    config = AnalyzerConfig(provider="mock")
    analyzer = LLMStreamAnalyzer(config)

    results: list[AnalysisResult] = []

    async def collect(r: AnalysisResult):
        results.append(r)

    analyzer.set_on_analysis(collect)

    # 直接_analyzeを呼ぶ (ZMQ不要)
    await analyzer._analyze("user@host:~$ ls\nfile1.txt  file2.txt")
    await asyncio.sleep(0.1)

    if not results:
        return False

    r = results[0]
    return r.threat_level == "none" and r.model_used == "mock"


async def test_analyzer_mock_threat_high() -> bool:
    """LLMStreamAnalyzer: モック - 高脅威コマンド"""
    config = AnalyzerConfig(provider="mock")
    analyzer = LLMStreamAnalyzer(config)

    results: list[AnalysisResult] = []

    async def collect(r: AnalysisResult):
        results.append(r)

    analyzer.set_on_analysis(collect)

    await analyzer._analyze("root@host:~# rm -rf /")
    await asyncio.sleep(0.1)

    if not results:
        return False

    return results[0].threat_level == "high"


async def test_analyzer_mock_threat_medium() -> bool:
    """LLMStreamAnalyzer: モック - 中脅威コマンド"""
    config = AnalyzerConfig(provider="mock")
    analyzer = LLMStreamAnalyzer(config)

    results: list[AnalysisResult] = []

    async def collect(r: AnalysisResult):
        results.append(r)

    analyzer.set_on_analysis(collect)

    await analyzer._analyze("$ sudo apt install something")
    await asyncio.sleep(0.1)

    if not results:
        return False

    return results[0].threat_level == "medium"


async def test_analyzer_token_budget() -> bool:
    """LLMStreamAnalyzer: トークンバジェット制御"""
    config = AnalyzerConfig(provider="mock", max_tokens_per_minute=0)
    analyzer = LLMStreamAnalyzer(config)

    # バジェット=0なのでスキップされるはず
    results: list[AnalysisResult] = []

    async def collect(r: AnalysisResult):
        results.append(r)

    analyzer.set_on_analysis(collect)

    await analyzer._analyze("test output")
    await asyncio.sleep(0.1)

    # バジェット超過でスキップ → 結果なし
    return len(results) == 0


async def test_analyzer_parse_response() -> bool:
    """LLMStreamAnalyzer: レスポンスパース"""
    config = AnalyzerConfig(provider="mock")
    analyzer = LLMStreamAnalyzer(config)

    # 正常JSON
    r1 = analyzer._parse_response(
        '{"threat_level": "high", "insight": "test", "recommendation": "stop"}',
        100,
    )
    if r1.threat_level != "high" or r1.insight != "test":
        return False

    # マークダウンフェンス付き
    r2 = analyzer._parse_response(
        '```json\n{"threat_level": "low", "insight": "ok", "recommendation": ""}\n```',
        50,
    )
    if r2.threat_level != "low":
        return False

    # 不正JSON → エラー付き結果
    r3 = analyzer._parse_response("not valid json", 10)
    if not r3.error:
        return False

    return True


async def test_analyzer_build_messages() -> bool:
    """LLMStreamAnalyzer: メッセージ構築"""
    config = AnalyzerConfig(provider="mock")
    analyzer = LLMStreamAnalyzer(config)

    # コマンド履歴なし
    msgs = analyzer._build_messages("test output")
    if len(msgs) != 2:  # system + user
        return False
    if msgs[0]["role"] != "system":
        return False
    if "test output" not in msgs[1]["content"]:
        return False

    # コマンド履歴あり
    analyzer._command_history = ["$ ls", "$ pwd"]
    msgs = analyzer._build_messages("output")
    if len(msgs) != 4:  # system + history_user + history_assistant + user
        return False

    return True


async def test_analyzer_build_messages_truncation() -> bool:
    """LLMStreamAnalyzer: 長いテキストの切り詰め"""
    config = AnalyzerConfig(provider="mock")
    analyzer = LLMStreamAnalyzer(config)

    long_text = "X" * 8000
    msgs = analyzer._build_messages(long_text)
    # 切り詰めマーカーが含まれるはず
    return "(truncated)" in msgs[-1]["content"]


# ==== テスト実行 ====


async def run_tests() -> None:
    print("\n=== LLM Stream Analyzer Tests ===\n")

    tests = [
        # ANSIストリッパー
        ("ANSI: basic SGR", test_strip_ansi_basic),
        ("ANSI: CSI sequences", test_strip_ansi_csi),
        ("ANSI: OSC sequences", test_strip_ansi_osc),
        ("ANSI: preserve newlines/tabs", test_strip_ansi_preserves_newlines),
        ("ANSI: empty input", test_strip_ansi_empty),
        ("ANSI: plain text passthrough", test_strip_ansi_plain_text),
        ("ANSI: 256/24bit color", test_strip_ansi_256color),
        ("ANSI: control chars", test_strip_ansi_control_chars),
        # デバウンスバッファ
        ("Debounce: size threshold", test_debounce_size_threshold),
        ("Debounce: timer flush", test_debounce_timer_flush),
        ("Debounce: accumulation", test_debounce_accumulation),
        ("Debounce: empty buffer", test_debounce_empty_buffer),
        # LLMStreamAnalyzer
        ("Analyzer: mock normal", test_analyzer_mock_normal),
        ("Analyzer: mock high threat", test_analyzer_mock_threat_high),
        ("Analyzer: mock medium threat", test_analyzer_mock_threat_medium),
        ("Analyzer: token budget", test_analyzer_token_budget),
        ("Analyzer: parse response", test_analyzer_parse_response),
        ("Analyzer: build messages", test_analyzer_build_messages),
        ("Analyzer: message truncation", test_analyzer_build_messages_truncation),
    ]

    passed = 0
    failed = 0
    start = time.time()

    for name, test_fn in tests:
        try:
            ok = await test_fn()
            result(name, ok)
            if ok:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            result(name, False, str(e))
            failed += 1

    elapsed = time.time() - start
    print(
        f"\n  Total: {passed + failed}, Passed: {passed}, "
        f"Failed: {failed}, Time: {elapsed:.1f}s\n"
    )

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_tests())

#!/usr/bin/env python3
"""フィージビリティスタディ: LLMストリーム分析付きシェル

PTYオープン + ZMQリモート制御 + LLMリアルタイム分析の統合デモ。

使い方:
  # モックプロバイダー (LLM接続なし)
  python run_analyzed_shell.py --provider mock

  # OpenAI
  python run_analyzed_shell.py --provider openai --model gpt-4o-mini

  # Anthropic
  python run_analyzed_shell.py --provider anthropic --model claude-haiku-4-5-20251001

  # Ollama (ローカル)
  python run_analyzed_shell.py --provider ollama --model llama3.2 --api-base http://localhost:11434
"""

import argparse
import asyncio
import logging
import os
import signal
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from async_pty import AsyncPTY, InputMode
from stream_analyzer import AnalysisResult, AnalyzerConfig, LLMStreamAnalyzer
from zmq_remote import ZMQRemoteServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.FileHandler("analyzed_shell.log"), logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("run_analyzed_shell")


# ANSI色定義 (stderr出力用)
_COLORS = {
    "none": "\033[32m",      # green
    "low": "\033[33m",       # yellow
    "medium": "\033[35m",    # magenta
    "high": "\033[31m",      # red
    "critical": "\033[31;1m",  # bold red
}
_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"


def _format_analysis(result: AnalysisResult) -> str:
    """分析結果をカラー付きテキストに整形"""
    color = _COLORS.get(result.threat_level, _COLORS["none"])

    lines = [
        f"{_DIM}{'─' * 60}{_RESET}",
        f"{_BOLD}[Analysis]{_RESET} {color}{result.threat_level.upper()}{_RESET}"
        f" {_DIM}({result.latency_ms:.0f}ms, {result.model_used}){_RESET}",
    ]

    if result.insight:
        lines.append(f"  {result.insight}")

    if result.recommendation:
        lines.append(f"  {_DIM}→ {result.recommendation}{_RESET}")

    if result.error:
        lines.append(f"  \033[31mError: {result.error}{_RESET}")

    lines.append(f"{_DIM}{'─' * 60}{_RESET}")

    return "\n".join(lines)


class AnalyzedShell:
    """PTY + ZMQリモート制御 + LLMストリーム分析の統合"""

    def __init__(
        self,
        command: list[str] | None = None,
        initial_mode: InputMode = InputMode.NORMAL,
        control_port: int = 15555,
        output_port: int = 15556,
        analyzer_config: AnalyzerConfig | None = None,
    ):
        self._pty = AsyncPTY(command=command)
        self._zmq = ZMQRemoteServer(
            control_port=control_port,
            output_port=output_port,
        )
        self._initial_mode = initial_mode
        self._shutdown_event = asyncio.Event()

        # LLM分析器
        config = analyzer_config or AnalyzerConfig()
        config.output_port = output_port
        self._analyzer = LLMStreamAnalyzer(config)
        self._analyzer.set_on_analysis(self._handle_analysis)

    async def start(self) -> None:
        """起動: PTY + ZMQ + LLM分析器"""
        # ZMQサーバ起動
        self._zmq.set_on_input(self._handle_remote_input)
        self._zmq.set_on_resize(self._handle_remote_resize)
        self._zmq.set_on_mode_change(self._handle_mode_change)
        await self._zmq.start()

        # PTY起動
        self._pty.set_on_output(self._handle_pty_output)
        self._pty.set_on_exit(self._handle_pty_exit)
        await self._pty.start()

        # 初期モード設定
        self._pty.input_mode = self._initial_mode

        # LLM分析器起動 (ZMQ PUB/SUBの接続安定化のため少し待つ)
        await asyncio.sleep(0.3)
        await self._analyzer.start()

        logger.info("AnalyzedShell started")

        # stderrにバナー表示
        print(
            f"\n{_BOLD}=== AetherTerm LLM Stream Analyzer ==={_RESET}\n"
            f"  Provider: {self._analyzer._config.provider}\n"
            f"  Model: {self._analyzer._config.model}\n"
            f"  Debounce: {self._analyzer._config.debounce_interval}s / "
            f"{self._analyzer._config.max_buffer_bytes}B\n"
            f"{_DIM}  Analysis results will appear below terminal output{_RESET}\n",
            file=sys.stderr,
        )

        # シグナルハンドラ
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._signal_handler)

        # 終了待機
        await self._shutdown_event.wait()

    async def stop(self) -> None:
        """停止"""
        await self._analyzer.stop()
        await self._pty.stop()
        await self._zmq.stop()
        self._shutdown_event.set()
        logger.info("AnalyzedShell stopped")

    def _signal_handler(self) -> None:
        logger.info("Signal received, shutting down...")
        asyncio.ensure_future(self.stop())

    def _handle_pty_output(self, data: bytes) -> None:
        """PTY出力処理: stdoutに表示 + ZMQで配信"""
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
        asyncio.ensure_future(self._zmq.publish_output(data))

    def _handle_pty_exit(self, code: int) -> None:
        logger.info(f"PTY child exited with code {code}")
        asyncio.ensure_future(self._zmq.publish_exit(code))
        asyncio.ensure_future(self.stop())

    async def _handle_remote_input(self, data: bytes) -> None:
        await self._pty.write_input(data)

    async def _handle_remote_resize(self, rows: int, cols: int) -> None:
        await self._pty.resize(rows, cols)

    async def _handle_mode_change(self, mode: InputMode) -> None:
        self._pty.input_mode = mode

    async def _handle_analysis(self, result: AnalysisResult) -> None:
        """LLM分析結果をstderrにカラー表示"""
        formatted = _format_analysis(result)
        print(formatted, file=sys.stderr)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Experimental AgentShell with LLM Stream Analysis"
    )
    parser.add_argument(
        "--command", "-c",
        type=str,
        default=None,
        help="実行コマンド (デフォルト: bash)",
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["normal", "blocked", "remote"],
        default="normal",
        help="初期入力モード (デフォルト: normal)",
    )
    parser.add_argument(
        "--control-port",
        type=int,
        default=15555,
        help="ZMQ制御ポート (デフォルト: 15555)",
    )
    parser.add_argument(
        "--output-port",
        type=int,
        default=15556,
        help="ZMQ出力配信ポート (デフォルト: 15556)",
    )
    # LLM分析設定
    parser.add_argument(
        "--provider",
        type=str,
        default="mock",
        help="LLMプロバイダー: mock, openai, anthropic, ollama (デフォルト: mock)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o-mini",
        help="LLMモデル名 (デフォルト: gpt-4o-mini)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default="",
        help="LLM APIキー (環境変数OPENAI_API_KEY等も使用可)",
    )
    parser.add_argument(
        "--api-base",
        type=str,
        default="",
        help="LLM APIベースURL (Ollama等のローカルLLM用)",
    )
    parser.add_argument(
        "--analyzer-interval",
        type=float,
        default=0.5,
        help="分析デバウンス間隔 秒 (デフォルト: 0.5)",
    )
    parser.add_argument(
        "--max-buffer",
        type=int,
        default=4096,
        help="分析バッファ最大サイズ バイト (デフォルト: 4096)",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    command = args.command.split() if args.command else None
    mode_map = {
        "normal": InputMode.NORMAL,
        "blocked": InputMode.BLOCKED,
        "remote": InputMode.REMOTE,
    }

    analyzer_config = AnalyzerConfig(
        provider=args.provider,
        model=args.model,
        api_key=args.api_key,
        api_base=args.api_base,
        debounce_interval=args.analyzer_interval,
        max_buffer_bytes=args.max_buffer,
        output_port=args.output_port,
    )

    shell = AnalyzedShell(
        command=command,
        initial_mode=mode_map[args.mode],
        control_port=args.control_port,
        output_port=args.output_port,
        analyzer_config=analyzer_config,
    )

    try:
        await shell.start()
    except KeyboardInterrupt:
        pass
    finally:
        await shell.stop()


if __name__ == "__main__":
    asyncio.run(main())

"""LLMストリーム分析 - PTY出力をリアルタイムでLLM分析

ZMQ SUBでPTY出力を受信し、デバウンスバッファで集約後、
litellm経由でLLMストリーミング分析を行う。

アーキテクチャ:
  ZMQ SUB (:15556) → ANSIストリップ → デバウンスバッファ → litellm → 分析結果
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import zmq
import zmq.asyncio

from ansi_stripper import strip_ansi

logger = logging.getLogger(__name__)


@dataclass
class AnalyzerConfig:
    """LLMストリーム分析設定"""

    # LLM設定
    provider: str = "mock"  # "openai", "anthropic", "ollama", "mock"
    model: str = "gpt-4o-mini"
    api_key: str = ""
    api_base: str = ""

    # デバウンス設定
    debounce_interval: float = 0.5  # 秒
    max_buffer_bytes: int = 4096  # バイト

    # ZMQ設定
    output_port: int = 15556
    server_addr: str = "tcp://localhost"

    # トークンバジェット
    max_tokens_per_minute: int = 10000
    max_concurrent: int = 1

    # コンテキスト
    command_history_size: int = 5

    # 分析プロンプト
    system_prompt: str = (
        "You are a terminal security analyzer. Analyze the following terminal output "
        "and provide a brief assessment.\n"
        "Respond in JSON format ONLY:\n"
        '{"threat_level": "none|low|medium|high|critical", '
        '"insight": "<brief description of what is happening>", '
        '"recommendation": "<action to take, if any>"}\n'
        "Be concise. Focus on security-relevant observations."
    )


@dataclass
class AnalysisResult:
    """分析結果"""

    threat_level: str = "none"
    insight: str = ""
    recommendation: str = ""
    model_used: str = ""
    tokens_used: int = 0
    latency_ms: float = 0.0
    error: str = ""


class DebounceBuffer:
    """時間 or サイズ閾値でフラッシュするデバウンスバッファ

    - interval秒以内に新データが来ればタイマーリセット
    - max_bytesを超えたら即フラッシュ
    """

    def __init__(
        self,
        interval: float = 0.5,
        max_bytes: int = 4096,
    ):
        self._interval = interval
        self._max_bytes = max_bytes
        self._buffer: list[str] = []
        self._buffer_size = 0
        self._timer_handle: Optional[asyncio.TimerHandle] = None
        self._flush_event = asyncio.Event()
        self._pending_text: Optional[str] = None
        self._lock = asyncio.Lock()

    async def add(self, text: str) -> Optional[str]:
        """テキストをバッファに追加。フラッシュ条件を満たしたらテキストを返す"""
        async with self._lock:
            self._buffer.append(text)
            self._buffer_size += len(text.encode("utf-8"))

            # サイズ閾値超過 → 即フラッシュ
            if self._buffer_size >= self._max_bytes:
                return self._do_flush()

            # タイマーリセット
            self._reset_timer()
            return None

    async def wait_flush(self) -> Optional[str]:
        """タイマーによるフラッシュを待つ"""
        self._flush_event.clear()
        await self._flush_event.wait()
        async with self._lock:
            if self._pending_text:
                text = self._pending_text
                self._pending_text = None
                return text
        return None

    def _do_flush(self) -> Optional[str]:
        """バッファをフラッシュしてテキストを返す"""
        if not self._buffer:
            return None
        text = "".join(self._buffer)
        self._buffer.clear()
        self._buffer_size = 0
        self._cancel_timer()
        return text

    def _reset_timer(self) -> None:
        """デバウンスタイマーをリセット"""
        self._cancel_timer()
        loop = asyncio.get_running_loop()
        self._timer_handle = loop.call_later(self._interval, self._timer_callback)

    def _cancel_timer(self) -> None:
        if self._timer_handle:
            self._timer_handle.cancel()
            self._timer_handle = None

    def _timer_callback(self) -> None:
        """タイマー満了時のコールバック"""
        text = self._do_flush()
        if text:
            self._pending_text = text
            self._flush_event.set()

    @property
    def buffered_size(self) -> int:
        return self._buffer_size


class LLMStreamAnalyzer:
    """PTY出力のLLMストリーム分析器

    ZMQ SUBでPTY出力を受信 → ANSIストリップ → デバウンスバッファ → litellm分析
    """

    def __init__(self, config: AnalyzerConfig):
        self._config = config
        self._buffer = DebounceBuffer(
            interval=config.debounce_interval,
            max_bytes=config.max_buffer_bytes,
        )

        # ZMQ
        self._ctx: Optional[zmq.asyncio.Context] = None
        self._sub: Optional[zmq.asyncio.Socket] = None

        # 状態
        self._running = False
        self._command_history: list[str] = []
        self._analysis_count = 0
        self._total_tokens = 0
        self._token_window_start = time.monotonic()
        self._token_window_count = 0

        # asyncioタスク
        self._recv_task: Optional[asyncio.Task] = None
        self._flush_task: Optional[asyncio.Task] = None

        # コールバック
        self._on_analysis: Optional[callable] = None

    def set_on_analysis(self, callback) -> None:
        """分析結果コールバック: async (AnalysisResult) -> None"""
        self._on_analysis = callback

    async def start(self) -> None:
        """分析開始: ZMQ SUB接続 + 受信ループ起動"""
        if self._running:
            return

        self._ctx = zmq.asyncio.Context()
        self._sub = self._ctx.socket(zmq.SUB)
        self._sub.connect(f"{self._config.server_addr}:{self._config.output_port}")
        self._sub.subscribe(b"output")

        self._running = True
        self._token_window_start = time.monotonic()

        self._recv_task = asyncio.create_task(self._recv_loop())
        self._flush_task = asyncio.create_task(self._flush_loop())

        logger.info(
            f"LLMStreamAnalyzer started: provider={self._config.provider}, "
            f"model={self._config.model}, port={self._config.output_port}"
        )

    async def stop(self) -> None:
        """分析停止"""
        if not self._running:
            return
        self._running = False

        for task in [self._recv_task, self._flush_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        if self._sub:
            self._sub.close()
        if self._ctx:
            self._ctx.term()

        logger.info(
            f"LLMStreamAnalyzer stopped: analyses={self._analysis_count}, "
            f"total_tokens={self._total_tokens}"
        )

    async def _recv_loop(self) -> None:
        """ZMQ SUBからPTY出力を受信してバッファに追加"""
        try:
            while self._running:
                try:
                    frames = await asyncio.wait_for(
                        self._sub.recv_multipart(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                if len(frames) < 2 or frames[0] != b"output":
                    continue

                raw_data = frames[1]
                text = strip_ansi(raw_data)

                if not text.strip():
                    continue

                # コマンド履歴更新 (改行を含む入力をコマンドとみなす)
                self._update_command_history(text)

                # バッファに追加 → サイズ超過時は即分析
                flushed = await self._buffer.add(text)
                if flushed:
                    asyncio.create_task(self._analyze(flushed))

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Recv loop error: {e}")

    async def _flush_loop(self) -> None:
        """デバウンスタイマーによるフラッシュを待って分析"""
        try:
            while self._running:
                flushed = await self._buffer.wait_flush()
                if flushed:
                    await self._analyze(flushed)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Flush loop error: {e}")

    def _update_command_history(self, text: str) -> None:
        """簡易コマンド履歴更新"""
        lines = text.strip().split("\n")
        for line in lines:
            stripped = line.strip()
            # プロンプト行っぽいものをコマンドとして記録
            if stripped and ("$" in stripped or "#" in stripped or ">>>" in stripped):
                self._command_history.append(stripped)
                if len(self._command_history) > self._config.command_history_size:
                    self._command_history.pop(0)

    async def _analyze(self, text: str) -> None:
        """テキストをLLMで分析"""
        # トークンバジェットチェック
        if not self._check_token_budget():
            logger.debug("Token budget exceeded, skipping analysis")
            return

        start_time = time.monotonic()

        try:
            result = await self._call_llm(text)
        except Exception as e:
            result = AnalysisResult(error=str(e))
            logger.warning(f"LLM analysis error: {e}")

        result.latency_ms = (time.monotonic() - start_time) * 1000
        self._analysis_count += 1

        if self._on_analysis:
            await self._on_analysis(result)

    def _check_token_budget(self) -> bool:
        """トークンバジェット制チェック (1分ウィンドウ)"""
        now = time.monotonic()
        elapsed = now - self._token_window_start

        if elapsed >= 60.0:
            # ウィンドウリセット
            self._token_window_start = now
            self._token_window_count = 0
            return True

        return self._token_window_count < self._config.max_tokens_per_minute

    def _build_messages(self, text: str) -> list[dict[str, str]]:
        """LLMに送るメッセージを構築"""
        messages = [{"role": "system", "content": self._config.system_prompt}]

        # コマンド履歴コンテキスト
        if self._command_history:
            context = "Recent command history:\n" + "\n".join(self._command_history[-5:])
            messages.append({"role": "user", "content": context})
            messages.append({
                "role": "assistant",
                "content": "Understood. I'll analyze the next output with this context.",
            })

        # 分析対象テキスト
        # 長すぎる場合は末尾4KBに切り詰め
        if len(text) > 4096:
            text = "...(truncated)...\n" + text[-4096:]

        messages.append({"role": "user", "content": f"Terminal output:\n```\n{text}\n```"})

        return messages

    async def _call_llm(self, text: str) -> AnalysisResult:
        """litellm経由でLLM分析を実行"""
        if self._config.provider == "mock":
            return await self._mock_analyze(text)

        import litellm

        messages = self._build_messages(text)

        kwargs: dict = {
            "model": self._config.model,
            "messages": messages,
            "stream": True,
            "temperature": 0.1,
            "max_tokens": 256,
        }
        if self._config.api_key:
            kwargs["api_key"] = self._config.api_key
        if self._config.api_base:
            kwargs["api_base"] = self._config.api_base

        # ストリーミング応答の収集
        chunks: list[str] = []
        response = await litellm.acompletion(**kwargs)
        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                chunks.append(delta.content)

        content = "".join(chunks)

        # トークンカウント（概算: 4文字≒1トークン）
        estimated_tokens = len(content) // 4 + sum(len(m["content"]) for m in messages) // 4
        self._token_window_count += estimated_tokens
        self._total_tokens += estimated_tokens

        return self._parse_response(content, estimated_tokens)

    async def _mock_analyze(self, text: str) -> AnalysisResult:
        """モックプロバイダー: LLM呼出なしでダミー結果を返す"""
        await asyncio.sleep(0.05)  # 擬似レイテンシ

        # テキスト内容に基づく簡易判定
        threat_level = "none"
        insight = "Normal terminal activity"
        recommendation = ""

        lower = text.lower()
        if any(w in lower for w in ["rm -rf", "chmod 777", "dd if="]):
            threat_level = "high"
            insight = "Potentially destructive command detected"
            recommendation = "Review command before execution"
        elif any(w in lower for w in ["sudo", "su ", "passwd"]):
            threat_level = "medium"
            insight = "Privilege escalation command detected"
            recommendation = "Verify authorization"
        elif any(w in lower for w in ["curl", "wget", "nc ", "ncat"]):
            threat_level = "low"
            insight = "Network operation detected"
            recommendation = "Monitor target URL"
        elif "error" in lower or "fail" in lower:
            threat_level = "low"
            insight = "Error output detected"
            recommendation = "Check error details"

        return AnalysisResult(
            threat_level=threat_level,
            insight=insight,
            recommendation=recommendation,
            model_used="mock",
            tokens_used=0,
        )

    def _parse_response(self, content: str, tokens: int) -> AnalysisResult:
        """LLMレスポンスをAnalysisResultにパース"""
        try:
            # マークダウンフェンス除去
            cleaned = content.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                start = 1 if lines[0].startswith("```") else 0
                end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
                cleaned = "\n".join(lines[start:end])

            parsed = json.loads(cleaned)

            return AnalysisResult(
                threat_level=parsed.get("threat_level", "none"),
                insight=parsed.get("insight", ""),
                recommendation=parsed.get("recommendation", ""),
                model_used=self._config.model,
                tokens_used=tokens,
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return AnalysisResult(
                threat_level="none",
                insight=content[:200],
                recommendation="",
                model_used=self._config.model,
                tokens_used=tokens,
                error=f"Parse error: {e}",
            )

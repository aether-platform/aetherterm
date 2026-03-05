"""LLMLogAnalyzer - 汎用LLM APIによるログ分析

パターン圧縮済みログをLLMに渡し、異常検知・要約を行う。
LiteLLMを使用して複数プロバイダー（OpenAI/Anthropic/Azure等）に対応。
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from aetherterm.common.models import LogAnalysisResult

from .log_analysis_config import LogAnalysisConfig
from .log_pattern_compressor import CompressedLogBatch

logger = logging.getLogger(__name__)


class LLMClient(ABC):
    """LLMクライアントプロトコル"""

    @abstractmethod
    async def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        """LLM API呼び出し

        Returns:
            {"content": str, "usage": {"prompt_tokens": int, "completion_tokens": int}}
        """
        ...


class LiteLLMClient(LLMClient):
    """LiteLLM経由の汎用LLMクライアント"""

    def __init__(self, config: LogAnalysisConfig):
        self._model = config.llm_model
        self._timeout = config.llm_timeout_sec
        self._api_key = config.llm_api_key
        self._base_url = config.llm_base_url or None

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


class StubClient(LLMClient):
    """テスト・オフライン用スタブ"""

    def __init__(self, response: str | None = None):
        self._response = response

    async def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        if self._response:
            return {
                "content": self._response,
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            }

        return {
            "content": json.dumps({
                "anomalies": [],
                "summary": "No anomalies detected. Normal log activity.",
                "risk_level": "low",
            }),
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }


def _format_patterns_for_prompt(batch: CompressedLogBatch) -> str:
    """圧縮パターンをプロンプト用テキストに変換"""
    lines = []
    lines.append(f"Session: {batch.session_id}")
    lines.append(f"Total lines: {batch.total_lines}, Unique patterns: {batch.unique_patterns}")
    lines.append(f"Compression ratio: {batch.compression_ratio:.1f}x")
    lines.append("")

    for i, pat in enumerate(batch.patterns, 1):
        lines.append(f"Pattern #{i} (count={pat.count}, severity={pat.severity}):")
        lines.append(f"  Normalized: {pat.normalized}")
        if pat.samples:
            lines.append(f"  Sample: {pat.samples[0]}")
        lines.append("")

    return "\n".join(lines)


_ANOMALY_PROMPT = """\
You are a security-focused log analyzer for a terminal management system.
Analyze the following compressed log patterns and identify anomalies or threats.

{patterns}

Respond in JSON format ONLY (no markdown fences):
{{
  "anomalies": [
    {{
      "pattern": "<the normalized pattern>",
      "severity": "low|medium|high|critical",
      "description": "<what this anomaly indicates>",
      "recommended_action": "<suggested response>"
    }}
  ],
  "risk_level": "low|medium|high|critical",
  "summary": "<brief overall assessment>"
}}

Focus on:
- Unauthorized access attempts
- Privilege escalation
- Data exfiltration indicators
- Suspicious command patterns (rm -rf, wget/curl to unknown hosts, reverse shells)
- Repeated errors suggesting system compromise
- Unusual patterns for a terminal session

If no anomalies are found, return empty anomalies list with risk_level "low"."""

_SUMMARY_PROMPT = """\
You are a log analyst for a terminal management system.
Summarize the following compressed log patterns, highlighting key events and trends.

{patterns}

Respond in JSON format ONLY (no markdown fences):
{{
  "summary": "<comprehensive summary of log activity>",
  "key_events": ["<event1>", "<event2>"],
  "trends": ["<trend1>", "<trend2>"],
  "risk_level": "low|medium|high|critical"
}}"""


class LLMLogAnalyzer:
    """LLMベースのログ分析器"""

    def __init__(self, config: LogAnalysisConfig, client: LLMClient | None = None):
        self._config = config
        self._semaphore = asyncio.Semaphore(config.llm_max_concurrent)

        if client is not None:
            self._client = client
        elif config.llm_api_key:
            self._client = LiteLLMClient(config)
        else:
            logger.warning("No LLM API key configured, using StubClient")
            self._client = StubClient()

    async def analyze(self, batch: CompressedLogBatch) -> LogAnalysisResult:
        """圧縮ログバッチを分析"""
        mode = self._config.analysis_mode
        patterns_text = _format_patterns_for_prompt(batch)

        anomaly_result: dict = {}
        summary_result: dict = {}
        total_usage: dict = {"prompt_tokens": 0, "completion_tokens": 0}

        if mode in ("anomaly", "both"):
            anomaly_result, usage = await self._call_llm(
                _ANOMALY_PROMPT.format(patterns=patterns_text)
            )
            total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
            total_usage["completion_tokens"] += usage.get("completion_tokens", 0)

        if mode in ("summary", "both"):
            summary_result, usage = await self._call_llm(
                _SUMMARY_PROMPT.format(patterns=patterns_text)
            )
            total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
            total_usage["completion_tokens"] += usage.get("completion_tokens", 0)

        # 結果をマージ
        anomalies = anomaly_result.get("anomalies", [])
        risk_level = anomaly_result.get("risk_level", summary_result.get("risk_level", "low"))
        summary = summary_result.get("summary", anomaly_result.get("summary", ""))

        from datetime import datetime

        return LogAnalysisResult(
            session_id=batch.session_id,
            analysis_type=mode,
            anomalies=anomalies,
            summary=summary,
            risk_level=risk_level,
            timestamp=datetime.now().isoformat(),
            model_used=self._config.llm_model,
            token_usage=total_usage,
        )

    async def _call_llm(self, prompt: str) -> tuple[dict, dict]:
        """LLM APIを呼び出し、JSONレスポンスをパース"""
        async with self._semaphore:
            try:
                result = await self._client.complete(
                    [{"role": "user", "content": prompt}]
                )
                content = result["content"]
                usage = result.get("usage", {})

                # JSONパース（マークダウンフェンス除去）
                cleaned = content.strip()
                if cleaned.startswith("```"):
                    # ```json ... ``` を除去
                    lines = cleaned.split("\n")
                    start = 1 if lines[0].startswith("```") else 0
                    end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
                    cleaned = "\n".join(lines[start:end])

                parsed = json.loads(cleaned)
                return parsed, usage

            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse LLM response as JSON: {e}")
                return {"summary": content, "risk_level": "low", "anomalies": []}, usage
            except Exception as e:
                logger.exception(f"LLM call failed: {e}")
                return {
                    "summary": f"Analysis unavailable: {e}",
                    "risk_level": "low",
                    "anomalies": [],
                }, {}

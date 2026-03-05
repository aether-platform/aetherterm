"""
Local AI provider (Ollama, etc.).
"""

import logging
from typing import Any, Dict, List

import aiohttp

from .base import AIProvider

logger = logging.getLogger(__name__)


class LocalProvider(AIProvider):
    """Local AI provider (Ollama, etc.)."""

    def __init__(
        self, api_key: str = "", model: str = "llama2", endpoint: str = "http://localhost:11434"
    ):
        super().__init__(api_key, model, endpoint)

    async def analyze_command_output(
        self, command: str, output: str, exit_code: int, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        try:
            prompt = f"コマンド '{command}' の実行結果（終了コード: {exit_code}）を分析してください:\n{output}"
            response = await self._call_api(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"Local AI API error: {e}")
            return {"error": str(e), "analysis": None}

    async def suggest_error_fix(
        self, command: str, error_output: str, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        try:
            prompt = f"コマンド '{command}' でエラーが発生しました。修正方法を提案してください:\n{error_output}"
            response = await self._call_api(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"Local AI API error: {e}")
            return {"error": str(e), "suggestions": []}

    async def suggest_next_commands(
        self, command_history: List[str], current_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        try:
            history_str = "\n".join(command_history[-5:])
            prompt = f"以下のコマンド履歴に基づいて、次のコマンドを提案してください:\n{history_str}"
            response = await self._call_api(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"Local AI API error: {e}")
            return {"error": str(e), "suggestions": []}

    async def _call_api(self, prompt: str) -> Dict[str, Any]:
        """Call local AI API (Ollama format)."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.endpoint}/api/generate", json=payload) as response:
                if response.status == 200:
                    return await response.json()
                error_text = await response.text()
                raise Exception(f"Local AI API error: {response.status} - {error_text}")

    def _parse_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse local AI response."""
        try:
            content = response.get("response", "")
            return {
                "success": True,
                "severity": "low",
                "summary": content[:200],
                "insights": [content],
                "warnings": [],
                "recommendations": [],
            }
        except Exception as e:
            logger.error(f"Local AI response parse error: {e}")
            return {"error": "Failed to parse response"}

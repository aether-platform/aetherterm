"""
OpenAI API provider.
"""

import logging
from typing import Any, Dict, List

import aiohttp

from .base import AIProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(AIProvider):
    """OpenAI API provider."""

    def __init__(self, api_key: str, model: str = "gpt-4", endpoint: str = None):
        super().__init__(api_key, model, endpoint or "https://api.openai.com/v1")

    async def analyze_command_output(
        self, command: str, output: str, exit_code: int, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        try:
            prompt = self.build_analysis_prompt(command, output, exit_code, context)
            response = await self._call_api(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return {"error": str(e), "analysis": None}

    async def suggest_error_fix(
        self, command: str, error_output: str, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        try:
            prompt = self.build_error_fix_prompt(command, error_output, context)
            response = await self._call_api(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return {"error": str(e), "suggestions": []}

    async def suggest_next_commands(
        self, command_history: List[str], current_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        try:
            prompt = self.build_command_suggestion_prompt(command_history, current_context)
            response = await self._call_api(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return {"error": str(e), "suggestions": []}

    async def _call_api(self, prompt: str) -> Dict[str, Any]:
        """Call OpenAI API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "あなたはLinuxターミナルの専門家です。コマンドの実行結果を分析し、有用な洞察や提案を提供してください。",
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 1000,
            "temperature": 0.3,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.endpoint}/chat/completions", headers=headers, json=payload
            ) as response:
                if response.status == 200:
                    return await response.json()
                error_text = await response.text()
                raise Exception(f"OpenAI API error: {response.status} - {error_text}")

    def _parse_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse OpenAI response."""
        try:
            content = response["choices"][0]["message"]["content"]
            return self._parse_json_response(content)
        except KeyError as e:
            logger.error(f"OpenAI response parse error: {e}")
            return {"error": "Failed to parse response", "analysis": None}

"""
Anthropic Claude API provider.
"""

import logging
from typing import Any, Dict, List

import aiohttp

from .base import AIProvider

logger = logging.getLogger(__name__)


class AnthropicProvider(AIProvider):
    """Anthropic Claude API provider."""

    def __init__(self, api_key: str, model: str = "claude-3-sonnet-20240229", endpoint: str = None):
        super().__init__(api_key, model, endpoint or "https://api.anthropic.com/v1")

    async def analyze_command_output(
        self, command: str, output: str, exit_code: int, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        try:
            prompt = self.build_analysis_prompt(command, output, exit_code, context)
            response = await self._call_api(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            return {"error": str(e), "analysis": None}

    async def suggest_error_fix(
        self, command: str, error_output: str, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        try:
            prompt = self.build_error_fix_prompt(command, error_output, context)
            response = await self._call_api(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            return {"error": str(e), "suggestions": []}

    async def suggest_next_commands(
        self, command_history: List[str], current_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        try:
            prompt = self.build_command_suggestion_prompt(command_history, current_context)
            response = await self._call_api(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            return {"error": str(e), "suggestions": []}

    async def _call_api(self, prompt: str) -> Dict[str, Any]:
        """Call Anthropic API."""
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        payload = {
            "model": self.model,
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": prompt}],
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.endpoint}/messages", headers=headers, json=payload
            ) as response:
                if response.status == 200:
                    return await response.json()
                error_text = await response.text()
                raise Exception(f"Anthropic API error: {response.status} - {error_text}")

    def _parse_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Anthropic response."""
        try:
            content = response["content"][0]["text"]
            return self._parse_json_response(content)
        except KeyError as e:
            logger.error(f"Anthropic response parse error: {e}")
            return {"error": "Failed to parse response"}

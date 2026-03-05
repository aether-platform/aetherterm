"""
Abstract base class for AI providers with shared prompt building.
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class AIProvider(ABC):
    """AI provider abstract base class."""

    def __init__(self, api_key: str, model: str, endpoint: str = None):
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint

    @abstractmethod
    async def analyze_command_output(
        self, command: str, output: str, exit_code: int, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Analyze command output and return AI insights."""

    @abstractmethod
    async def suggest_error_fix(
        self, command: str, error_output: str, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Get error fix suggestions."""

    @abstractmethod
    async def suggest_next_commands(
        self, command_history: List[str], current_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Suggest next commands based on history."""

    # --- Shared prompt builders ---

    def _format_context(self, context: Dict[str, Any] = None) -> str:
        return json.dumps(context, ensure_ascii=False, indent=2) if context else "なし"

    def build_analysis_prompt(
        self, command: str, output: str, exit_code: int, context: Dict[str, Any] = None
    ) -> str:
        """Build command analysis prompt."""
        return f"""以下のコマンド実行結果を分析してください：

コマンド: {command}
終了コード: {exit_code}
出力:
{output}

コンテキスト:
{self._format_context(context)}

以下の形式でJSON応答してください：
{{
    "success": true/false,
    "severity": "low/medium/high",
    "summary": "実行結果の要約",
    "insights": ["洞察1", "洞察2"],
    "warnings": ["警告1", "警告2"],
    "recommendations": ["推奨事項1", "推奨事項2"]
}}"""

    def build_error_fix_prompt(
        self, command: str, error_output: str, context: Dict[str, Any] = None
    ) -> str:
        """Build error fix prompt."""
        return f"""以下のコマンドでエラーが発生しました。修正方法を提案してください：

コマンド: {command}
エラー出力:
{error_output}

コンテキスト:
{self._format_context(context)}

以下の形式でJSON応答してください：
{{
    "error_type": "エラーの種類",
    "cause": "エラーの原因",
    "fixes": [
        {{
            "description": "修正方法の説明",
            "command": "修正用コマンド",
            "confidence": 0.8
        }}
    ],
    "prevention": ["今後の予防策1", "今後の予防策2"]
}}"""

    def build_command_suggestion_prompt(
        self, command_history: List[str], current_context: Dict[str, Any] = None
    ) -> str:
        """Build command suggestion prompt."""
        history_str = "\n".join(command_history[-10:])
        return f"""以下のコマンド履歴に基づいて、次に実行すべきコマンドを提案してください：

コマンド履歴:
{history_str}

現在のコンテキスト:
{self._format_context(current_context)}

以下の形式でJSON応答してください：
{{
    "suggestions": [
        {{
            "command": "提案コマンド",
            "description": "コマンドの説明",
            "reason": "提案理由",
            "confidence": 0.8
        }}
    ],
    "workflow_suggestions": ["ワークフロー提案1", "ワークフロー提案2"]
}}"""

    def _parse_json_response(self, content: str, fallback_key: str = "analysis") -> Dict[str, Any]:
        """Parse JSON from AI response content."""
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return {"error": "Failed to parse response", fallback_key: None}

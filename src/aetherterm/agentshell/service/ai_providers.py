"""AIプロバイダーの抽象化と実装

直接AIサービス（OpenAI、Anthropic等）と通信し、
AetherTermサーバーに依存しない独立したAI機能を提供します。
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List

import aiohttp

logger = logging.getLogger(__name__)


class AIProvider(ABC):
    """AIプロバイダーの抽象基底クラス"""

    def __init__(self, api_key: str, model: str, endpoint: str = None):
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint

    @abstractmethod
    async def analyze_command_output(
        self, command: str, output: str, exit_code: int, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """コマンド出力を解析してAIの洞察を取得

        Args:
            command: 実行されたコマンド
            output: コマンドの出力
            exit_code: 終了コード
            context: 追加のコンテキスト

        Returns:
            Dict[str, Any]: AI解析結果
        """

    @abstractmethod
    async def suggest_error_fix(
        self, command: str, error_output: str, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """エラーの修正提案を取得

        Args:
            command: 実行されたコマンド
            error_output: エラー出力
            context: 追加のコンテキスト

        Returns:
            Dict[str, Any]: 修正提案
        """

    @abstractmethod
    async def suggest_next_commands(
        self, command_history: List[str], current_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """次のコマンドを提案

        Args:
            command_history: コマンド履歴
            current_context: 現在のコンテキスト

        Returns:
            Dict[str, Any]: コマンド提案
        """


class OpenAIProvider(AIProvider):
    """OpenAI APIプロバイダー"""

    def __init__(self, api_key: str, model: str = "gpt-4", endpoint: str = None):
        super().__init__(api_key, model, endpoint or "https://api.openai.com/v1")

    async def analyze_command_output(
        self, command: str, output: str, exit_code: int, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """OpenAI APIを使用してコマンド出力を解析"""
        try:
            prompt = self._build_analysis_prompt(command, output, exit_code, context)
            response = await self._call_openai_api(prompt)
            return self._parse_analysis_response(response)
        except Exception as e:
            logger.error(f"OpenAI API呼び出しエラー: {e}")
            return {"error": str(e), "analysis": None}

    async def suggest_error_fix(
        self, command: str, error_output: str, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """OpenAI APIを使用してエラー修正提案を取得"""
        try:
            prompt = self._build_error_fix_prompt(command, error_output, context)
            response = await self._call_openai_api(prompt)
            return self._parse_fix_response(response)
        except Exception as e:
            logger.error(f"OpenAI API呼び出しエラー: {e}")
            return {"error": str(e), "suggestions": []}

    async def suggest_next_commands(
        self, command_history: List[str], current_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """OpenAI APIを使用して次のコマンドを提案"""
        try:
            prompt = self._build_command_suggestion_prompt(command_history, current_context)
            response = await self._call_openai_api(prompt)
            return self._parse_suggestion_response(response)
        except Exception as e:
            logger.error(f"OpenAI API呼び出しエラー: {e}")
            return {"error": str(e), "suggestions": []}

    async def _call_openai_api(self, prompt: str) -> Dict[str, Any]:
        """OpenAI APIを呼び出し"""
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

    def _build_analysis_prompt(
        self, command: str, output: str, exit_code: int, context: Dict[str, Any] = None
    ) -> str:
        """コマンド解析用のプロンプトを構築"""
        context_str = json.dumps(context, ensure_ascii=False, indent=2) if context else "なし"

        return f"""
以下のコマンド実行結果を分析してください：

コマンド: {command}
終了コード: {exit_code}
出力:
{output}

コンテキスト:
{context_str}

以下の形式でJSON応答してください：
{{
    "success": true/false,
    "severity": "low/medium/high",
    "summary": "実行結果の要約",
    "insights": ["洞察1", "洞察2"],
    "warnings": ["警告1", "警告2"],
    "recommendations": ["推奨事項1", "推奨事項2"]
}}
"""

    def _build_error_fix_prompt(
        self, command: str, error_output: str, context: Dict[str, Any] = None
    ) -> str:
        """エラー修正用のプロンプトを構築"""
        context_str = json.dumps(context, ensure_ascii=False, indent=2) if context else "なし"

        return f"""
以下のコマンドでエラーが発生しました。修正方法を提案してください：

コマンド: {command}
エラー出力:
{error_output}

コンテキスト:
{context_str}

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
}}
"""

    def _build_command_suggestion_prompt(
        self, command_history: List[str], current_context: Dict[str, Any] = None
    ) -> str:
        """コマンド提案用のプロンプトを構築"""
        history_str = "\n".join(command_history[-10:])  # 最新10件
        context_str = (
            json.dumps(current_context, ensure_ascii=False, indent=2) if current_context else "なし"
        )

        return f"""
以下のコマンド履歴に基づいて、次に実行すべきコマンドを提案してください：

コマンド履歴:
{history_str}

現在のコンテキスト:
{context_str}

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
}}
"""

    def _parse_analysis_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """解析レスポンスをパース"""
        try:
            content = response["choices"][0]["message"]["content"]
            return json.loads(content)
        except (KeyError, json.JSONDecodeError) as e:
            logger.error(f"OpenAI応答のパースエラー: {e}")
            return {"error": "応答のパースに失敗", "analysis": None}

    def _parse_fix_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """修正提案レスポンスをパース"""
        try:
            content = response["choices"][0]["message"]["content"]
            return json.loads(content)
        except (KeyError, json.JSONDecodeError) as e:
            logger.error(f"OpenAI応答のパースエラー: {e}")
            return {"error": "応答のパースに失敗", "suggestions": []}

    def _parse_suggestion_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """コマンド提案レスポンスをパース"""
        try:
            content = response["choices"][0]["message"]["content"]
            return json.loads(content)
        except (KeyError, json.JSONDecodeError) as e:
            logger.error(f"OpenAI応答のパースエラー: {e}")
            return {"error": "応答のパースに失敗", "suggestions": []}


class AnthropicProvider(AIProvider):
    """Anthropic Claude APIプロバイダー"""

    def __init__(self, api_key: str, model: str = "claude-3-sonnet-20240229", endpoint: str = None):
        super().__init__(api_key, model, endpoint or "https://api.anthropic.com/v1")

    async def analyze_command_output(
        self, command: str, output: str, exit_code: int, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Anthropic APIを使用してコマンド出力を解析"""
        try:
            prompt = self._build_analysis_prompt(command, output, exit_code, context)
            response = await self._call_anthropic_api(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"Anthropic API呼び出しエラー: {e}")
            return {"error": str(e), "analysis": None}

    async def suggest_error_fix(
        self, command: str, error_output: str, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Anthropic APIを使用してエラー修正提案を取得"""
        try:
            prompt = self._build_error_fix_prompt(command, error_output, context)
            response = await self._call_anthropic_api(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"Anthropic API呼び出しエラー: {e}")
            return {"error": str(e), "suggestions": []}

    async def suggest_next_commands(
        self, command_history: List[str], current_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Anthropic APIを使用して次のコマンドを提案"""
        try:
            prompt = self._build_command_suggestion_prompt(command_history, current_context)
            response = await self._call_anthropic_api(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"Anthropic API呼び出しエラー: {e}")
            return {"error": str(e), "suggestions": []}

    async def _call_anthropic_api(self, prompt: str) -> Dict[str, Any]:
        """Anthropic APIを呼び出し"""
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

    def _build_analysis_prompt(
        self, command: str, output: str, exit_code: int, context: Dict[str, Any] = None
    ) -> str:
        """コマンド解析用のプロンプトを構築（OpenAIと同じ形式）"""
        context_str = json.dumps(context, ensure_ascii=False, indent=2) if context else "なし"

        return f"""
以下のコマンド実行結果を分析してください：

コマンド: {command}
終了コード: {exit_code}
出力:
{output}

コンテキスト:
{context_str}

以下の形式でJSON応答してください：
{{
    "success": true/false,
    "severity": "low/medium/high",
    "summary": "実行結果の要約",
    "insights": ["洞察1", "洞察2"],
    "warnings": ["警告1", "警告2"],
    "recommendations": ["推奨事項1", "推奨事項2"]
}}
"""

    def _build_error_fix_prompt(
        self, command: str, error_output: str, context: Dict[str, Any] = None
    ) -> str:
        """エラー修正用のプロンプトを構築（OpenAIと同じ形式）"""
        context_str = json.dumps(context, ensure_ascii=False, indent=2) if context else "なし"

        return f"""
以下のコマンドでエラーが発生しました。修正方法を提案してください：

コマンド: {command}
エラー出力:
{error_output}

コンテキスト:
{context_str}

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
}}
"""

    def _build_command_suggestion_prompt(
        self, command_history: List[str], current_context: Dict[str, Any] = None
    ) -> str:
        """コマンド提案用のプロンプトを構築（OpenAIと同じ形式）"""
        history_str = "\n".join(command_history[-10:])  # 最新10件
        context_str = (
            json.dumps(current_context, ensure_ascii=False, indent=2) if current_context else "なし"
        )

        return f"""
以下のコマンド履歴に基づいて、次に実行すべきコマンドを提案してください：

コマンド履歴:
{history_str}

現在のコンテキスト:
{context_str}

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
}}
"""

    def _parse_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Anthropic応答をパース"""
        try:
            content = response["content"][0]["text"]
            return json.loads(content)
        except (KeyError, json.JSONDecodeError) as e:
            logger.error(f"Anthropic応答のパースエラー: {e}")
            return {"error": "応答のパースに失敗"}


class LocalProvider(AIProvider):
    """ローカルAIプロバイダー（Ollama等）"""

    def __init__(
        self, api_key: str = "", model: str = "llama2", endpoint: str = "http://localhost:11434"
    ):
        super().__init__(api_key, model, endpoint)

    async def analyze_command_output(
        self, command: str, output: str, exit_code: int, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """ローカルAIを使用してコマンド出力を解析"""
        try:
            prompt = self._build_analysis_prompt(command, output, exit_code, context)
            response = await self._call_local_api(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"ローカルAI API呼び出しエラー: {e}")
            return {"error": str(e), "analysis": None}

    async def suggest_error_fix(
        self, command: str, error_output: str, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """ローカルAIを使用してエラー修正提案を取得"""
        try:
            prompt = self._build_error_fix_prompt(command, error_output, context)
            response = await self._call_local_api(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"ローカルAI API呼び出しエラー: {e}")
            return {"error": str(e), "suggestions": []}

    async def suggest_next_commands(
        self, command_history: List[str], current_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """ローカルAIを使用して次のコマンドを提案"""
        try:
            prompt = self._build_command_suggestion_prompt(command_history, current_context)
            response = await self._call_local_api(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"ローカルAI API呼び出しエラー: {e}")
            return {"error": str(e), "suggestions": []}

    async def _call_local_api(self, prompt: str) -> Dict[str, Any]:
        """ローカルAI APIを呼び出し（Ollama形式）"""
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
                raise Exception(f"ローカルAI API error: {response.status} - {error_text}")

    def _build_analysis_prompt(
        self, command: str, output: str, exit_code: int, context: Dict[str, Any] = None
    ) -> str:
        """コマンド解析用のプロンプトを構築"""
        return f"コマンド '{command}' の実行結果（終了コード: {exit_code}）を分析してください:\n{output}"

    def _build_error_fix_prompt(
        self, command: str, error_output: str, context: Dict[str, Any] = None
    ) -> str:
        """エラー修正用のプロンプトを構築"""
        return f"コマンド '{command}' でエラーが発生しました。修正方法を提案してください:\n{error_output}"

    def _build_command_suggestion_prompt(
        self, command_history: List[str], current_context: Dict[str, Any] = None
    ) -> str:
        """コマンド提案用のプロンプトを構築"""
        history_str = "\n".join(command_history[-5:])  # 最新5件
        return f"以下のコマンド履歴に基づいて、次のコマンドを提案してください:\n{history_str}"

    def _parse_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """ローカルAI応答をパース"""
        try:
            content = response.get("response", "")
            # 簡単な解析結果を返す
            return {
                "success": True,
                "severity": "low",
                "summary": content[:200],  # 最初の200文字
                "insights": [content],
                "warnings": [],
                "recommendations": [],
            }
        except Exception as e:
            logger.error(f"ローカルAI応答のパースエラー: {e}")
            return {"error": "応答のパースに失敗"}


def create_ai_provider(
    provider_type: str, api_key: str, model: str, endpoint: str = None
) -> AIProvider:
    """AIプロバイダーのファクトリー関数"""
    if provider_type.lower() == "openai":
        return OpenAIProvider(api_key, model, endpoint)
    if provider_type.lower() == "anthropic":
        return AnthropicProvider(api_key, model, endpoint)
    if provider_type.lower() == "local":
        return LocalProvider(api_key, model, endpoint)
    raise ValueError(f"サポートされていないAIプロバイダー: {provider_type}")

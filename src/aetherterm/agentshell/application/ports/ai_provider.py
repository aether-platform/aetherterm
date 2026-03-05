"""
AIプロバイダーポート

AI分析機能の抽象化インターフェースを定義します。
具体的なAIプロバイダー（OpenAI, Anthropic, ローカルモデル等）に依存しません。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class AIProviderPort(ABC):
    """AIプロバイダーポート"""

    @abstractmethod
    async def analyze_command(self, command: str, context: Optional[str] = None) -> Dict[str, Any]:
        """コマンドを分析"""

    @abstractmethod
    async def suggest_fix(self, error_message: str, command: str) -> Optional[str]:
        """エラーに対する修正案を提案"""

    @abstractmethod
    async def is_available(self) -> bool:
        """プロバイダーが利用可能か確認"""

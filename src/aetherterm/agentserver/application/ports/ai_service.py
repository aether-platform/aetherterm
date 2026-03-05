"""
AIサービスポート

AI チャット機能の抽象化インターフェースを定義します。
具体的なAIプロバイダー（Anthropic, OpenAI等）に依存しません。
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Optional


class AIServicePort(ABC):
    """AIサービスポート"""

    @abstractmethod
    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        terminal_context: Optional[str] = None,
        stream: bool = True,
    ) -> AsyncGenerator[str, None]:
        """チャット応答を生成"""

    @abstractmethod
    async def is_available(self) -> bool:
        """サービスが利用可能か確認"""

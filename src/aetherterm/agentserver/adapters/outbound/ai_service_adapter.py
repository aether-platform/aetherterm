"""
AIサービスアダプター

既存の AIService 実装を AIServicePort にアダプトします。
"""

from collections.abc import AsyncGenerator
from typing import Optional

from ...ai_services import AIService
from ...application.ports.ai_service import AIServicePort


class AIServiceAdapter(AIServicePort):
    """既存の AIService を AIServicePort に適合させるアダプター"""

    def __init__(self, ai_service: AIService):
        self._service = ai_service

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        terminal_context: Optional[str] = None,
        stream: bool = True,
    ) -> AsyncGenerator[str, None]:
        async for chunk in self._service.chat_completion(
            messages=messages,
            terminal_context=terminal_context,
            stream=stream,
        ):
            yield chunk

    async def is_available(self) -> bool:
        return await self._service.is_available()

"""
AI Services for AetherTerm Assistant

This module provides AI chat functionality with support for multiple AI providers.
Currently supports Anthropic Claude with streaming responses.
"""

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Optional

log = logging.getLogger(__name__)


class AIService(ABC):
    """Abstract base class for AI services."""

    @abstractmethod
    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        terminal_context: Optional[str] = None,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """Generate AI chat completion."""

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the AI service is available."""


class AnthropicService(AIService):
    """Anthropic Claude AI service with streaming support."""

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022"):
        self.api_key = api_key
        self.model = model
        self._client = None

    async def _get_client(self):
        """Lazy initialization of Anthropic client."""
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
                log.info(f"Initialized Anthropic client with model: {self.model}")
            except ImportError:
                log.error("anthropic package not installed. Run: pip install anthropic")
                raise
            except Exception as e:
                log.error(f"Failed to initialize Anthropic client: {e}")
                raise
        return self._client

    async def is_available(self) -> bool:
        """Check if Anthropic service is available."""
        if not self.api_key:
            log.warning("Anthropic API key not configured")
            return False

        try:
            client = await self._get_client()
            # Test with a minimal request
            await client.messages.create(
                model=self.model,
                max_tokens=1,
                messages=[{"role": "user", "content": "test"}]
            )
            return True
        except Exception as e:
            log.error(f"Anthropic service not available: {e}")
            return False

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        terminal_context: Optional[str] = None,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """Generate streaming chat completion using Anthropic Claude."""

        try:
            client = await self._get_client()

            # Build system message with terminal context
            system_content = """You are Aether AI, an intelligent terminal assistant. You help users with:
- Terminal operations and command-line tasks
- Troubleshooting system issues
- Code analysis and debugging
- File system navigation
- Development workflows

Be concise, helpful, and practical in your responses. When suggesting commands, explain what they do."""

            if terminal_context:
                system_content += f"\n\nCurrent terminal context:\n```\n{terminal_context}\n```"

            # Convert messages to Anthropic format
            anthropic_messages = []
            for msg in messages:
                if msg.get("role") in ["user", "assistant"]:
                    anthropic_messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })

            if stream:
                log.info(f"Starting streaming chat completion with {len(anthropic_messages)} messages")

                async with client.messages.stream(
                    model=self.model,
                    max_tokens=4096,
                    system=system_content,
                    messages=anthropic_messages
                ) as stream:
                    async for text in stream.text_stream:
                        yield text

            else:
                log.info(f"Starting non-streaming chat completion with {len(anthropic_messages)} messages")

                response = await client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=system_content,
                    messages=anthropic_messages
                )

                yield response.content[0].text

        except Exception as e:
            log.error(f"Error in Anthropic chat completion: {e}")
            yield f"Sorry, I encountered an error: {e!s}"


class MockAIService(AIService):
    """Mock AI service for testing and development."""

    async def is_available(self) -> bool:
        return True

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        terminal_context: Optional[str] = None,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """Generate mock responses for testing."""

        user_message = messages[-1].get("content", "") if messages else ""

        # Generate contextual mock responses
        if "error" in user_message.lower():
            response = "I see you're encountering an error. Let me help you troubleshoot this issue. Could you share more details about when this error occurs?"
        elif "command" in user_message.lower() or "how to" in user_message.lower():
            response = f"For '{user_message}', I recommend checking the documentation first. Here are some common approaches you could try..."
        elif terminal_context and "pwd" in terminal_context:
            response = "I can see you're currently in a directory. Based on your terminal context, you might want to explore the current files with 'ls -la'."
        else:
            response = f"Thanks for your message: '{user_message}'. I'm here to help with terminal operations, troubleshooting, and development tasks. What would you like assistance with?"

        if stream:
            # Simulate streaming by yielding word by word
            words = response.split()
            for word in words:
                yield word + " "
                await asyncio.sleep(0.05)  # Simulate realistic typing speed
        else:
            yield response


def create_ai_service(
    provider: str = "mock",
    api_key: Optional[str] = None,
    model: Optional[str] = None
) -> AIService:
    """Factory function to create AI service instances."""

    if provider == "anthropic":
        api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            log.warning("Anthropic API key not found, falling back to mock service")
            return MockAIService()

        model = model or "claude-3-5-sonnet-20241022"
        return AnthropicService(api_key=api_key, model=model)

    if provider == "mock":
        return MockAIService()

    log.warning(f"Unknown AI provider: {provider}, falling back to mock service")
    return MockAIService()


# --- レガシーグローバル状態 ---
# 新規コードでは ApplicationContainer.ai_service を使用してください。
# application/ports/ai_service.py (AIServicePort) が抽象インターフェースです。
# 以下の関数はDIコンテナ初期化時の互換性のために残しています。

_ai_service: Optional[AIService] = None


def get_ai_service() -> AIService:
    """Get the current AI service instance.

    Note: 新規 socket handler は DI 経由で AIServicePort を受け取るため、
    この関数は互換性のために残されています。
    """
    global _ai_service
    if _ai_service is None:
        _ai_service = MockAIService()
    return _ai_service


def set_ai_service(service: AIService):
    """Set the global AI service instance.

    Note: ApplicationContainer の初期化時に呼ばれます。
    """
    global _ai_service
    _ai_service = service

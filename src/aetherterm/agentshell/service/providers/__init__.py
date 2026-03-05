"""
AI providers for AetherTerm AgentShell.

Each provider communicates directly with an AI service (OpenAI, Anthropic, local)
to provide independent AI capabilities without depending on AetherTerm server.
"""

from .anthropic import AnthropicProvider
from .base import AIProvider
from .local import LocalProvider
from .openai import OpenAIProvider

__all__ = [
    "AIProvider",
    "AnthropicProvider",
    "LocalProvider",
    "OpenAIProvider",
    "create_ai_provider",
]


def create_ai_provider(
    provider_type: str, api_key: str, model: str, endpoint: str = None
) -> AIProvider:
    """AI provider factory function."""
    providers = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "local": LocalProvider,
    }
    provider_cls = providers.get(provider_type.lower())
    if provider_cls is None:
        raise ValueError(f"Unsupported AI provider: {provider_type}")
    return provider_cls(api_key, model, endpoint)

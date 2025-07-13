"""Simplified Dependency Injection Container."""

import os
from aetherterm.agentserver.infrastructure.external.ai_service import AIService
from aetherterm.agentserver.infrastructure.common.memoization import memoize_method, cached_property


class SimpleContainer:
    """Simple container for dependency management."""

    def __init__(self):
        self.infrastructure = SimpleInfrastructure()


class SimpleInfrastructure:
    """Infrastructure services container."""

    def __init__(self):
        self._ai_service = None
        self._env_cache = {}  # Cache for environment variables

    @memoize_method(maxsize=10, ttl=300)  # Cache env vars for 5 minutes
    def _get_env_var(self, key: str, default: str = None) -> str:
        """Get environment variable with caching."""
        return os.getenv(key, default)

    def ai_service(self):
        """Get or create AI service instance."""
        if self._ai_service is None:
            # Get configuration from environment with caching
            provider = self._get_env_var("AI_PROVIDER", "lmstudio")
            api_key = self._get_env_var("AI_API_KEY", None)
            model = self._get_env_var("AI_MODEL", "default")
            lmstudio_url = self._get_env_var("LMSTUDIO_URL", "http://192.168.210.218:1234")

            self._ai_service = AIService(
                provider=provider, api_key=api_key, model=model, lmstudio_url=lmstudio_url
            )
        return self._ai_service


def setup_di_container():
    """Setup simplified DI container."""
    return SimpleContainer()


# Global container instance
_container = None


def get_container():
    """Get the global container instance."""
    global _container
    if _container is None:
        _container = setup_di_container()
    return _container

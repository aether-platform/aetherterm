"""
JupyterHub Authentication Service - Infrastructure Layer

Handles authentication with JupyterHub and user validation.
"""

import asyncio
import logging
import aiohttp
import json
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

log = logging.getLogger("aetherterm.infrastructure.jupyterhub_auth")


class JupyterHubAuthService:
    """Service for authenticating with JupyterHub and managing user sessions."""

    def __init__(
        self,
        hub_api_url: str = "http://hub:8081/hub/api",
        hub_api_token: Optional[str] = None,
        cache_duration_minutes: int = 30,
    ):
        self.hub_api_url = hub_api_url.rstrip("/")
        self.hub_api_token = hub_api_token
        self.cache_duration = timedelta(minutes=cache_duration_minutes)
        self.user_cache: Dict[str, Dict[str, Any]] = {}

    async def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Validate JupyterHub token and return user information.

        Args:
            token: JupyterHub OAuth token

        Returns:
            User information dict or None if invalid
        """
        if not token:
            return None

        # Check cache first
        cached_user = self._get_cached_user(token)
        if cached_user:
            return cached_user

        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"token {token}", "Content-Type": "application/json"}

                # Call JupyterHub API to validate token and get user info
                async with session.get(
                    f"{self.hub_api_url}/user",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        user_data = await response.json()

                        # Get additional user info if we have service token
                        if self.hub_api_token:
                            user_data = await self._enrich_user_data(user_data, session)

                        user_info = {
                            "username": user_data.get("name"),
                            "groups": user_data.get("groups", []),
                            "admin": user_data.get("admin", False),
                            "server": user_data.get("server"),
                            "pending": user_data.get("pending"),
                            "last_activity": user_data.get("last_activity"),
                            "created": user_data.get("created"),
                            "auth_model": user_data.get("auth_model", {}),
                            "validated_at": datetime.utcnow().isoformat(),
                        }

                        # Cache the user info
                        self._cache_user(token, user_info)

                        log.info(
                            f"Successfully validated JupyterHub token for user: {user_info['username']}"
                        )
                        return user_info

                    elif response.status == 401:
                        log.warning("Invalid JupyterHub token provided")
                        return None

                    else:
                        error_text = await response.text()
                        log.error(f"JupyterHub API error: {response.status} - {error_text}")
                        return None

        except asyncio.TimeoutError:
            log.error("Timeout while validating JupyterHub token")
            return None
        except Exception as e:
            log.error(f"Error validating JupyterHub token: {e}")
            return None

    async def _enrich_user_data(
        self, user_data: Dict[str, Any], session: aiohttp.ClientSession
    ) -> Dict[str, Any]:
        """
        Enrich user data with additional information using service token.

        Args:
            user_data: Basic user data from token validation
            session: Active aiohttp session

        Returns:
            Enriched user data
        """
        if not self.hub_api_token:
            return user_data

        try:
            username = user_data.get("name")
            headers = {
                "Authorization": f"token {self.hub_api_token}",
                "Content-Type": "application/json",
            }

            # Get detailed user info
            async with session.get(
                f"{self.hub_api_url}/users/{username}",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                if response.status == 200:
                    detailed_data = await response.json()
                    # Merge additional data
                    user_data.update(
                        {
                            "groups": detailed_data.get("groups", []),
                            "auth_model": detailed_data.get("auth_model", {}),
                            "admin": detailed_data.get("admin", False),
                        }
                    )

        except Exception as e:
            log.warning(f"Could not enrich user data: {e}")

        return user_data

    def _get_cached_user(self, token: str) -> Optional[Dict[str, Any]]:
        """Get user from cache if still valid."""
        if token in self.user_cache:
            cached_data = self.user_cache[token]
            validated_at = datetime.fromisoformat(cached_data["validated_at"])

            if datetime.utcnow() - validated_at < self.cache_duration:
                return cached_data
            else:
                # Remove expired cache entry
                del self.user_cache[token]

        return None

    def _cache_user(self, token: str, user_info: Dict[str, Any]) -> None:
        """Cache user information."""
        self.user_cache[token] = user_info

    def clear_cache(self) -> None:
        """Clear the user cache."""
        self.user_cache.clear()
        log.info("Cleared JupyterHub user cache")

    async def get_user_groups(self, username: str) -> list:
        """
        Get groups for a specific user.

        Args:
            username: Username to get groups for

        Returns:
            List of group names
        """
        if not self.hub_api_token:
            log.warning("No service token available for group lookup")
            return []

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"token {self.hub_api_token}",
                    "Content-Type": "application/json",
                }

                async with session.get(
                    f"{self.hub_api_url}/users/{username}",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    if response.status == 200:
                        user_data = await response.json()
                        return user_data.get("groups", [])
                    else:
                        log.warning(f"Could not get groups for user {username}: {response.status}")
                        return []

        except Exception as e:
            log.error(f"Error getting groups for user {username}: {e}")
            return []

    def extract_token_from_headers(self, headers: Dict[str, str]) -> Optional[str]:
        """
        Extract JupyterHub token from request headers.

        Args:
            headers: Request headers

        Returns:
            Token string or None
        """
        # Check Authorization header
        auth_header = headers.get("authorization") or headers.get("Authorization")
        if auth_header:
            if auth_header.startswith("token "):
                return auth_header[6:]  # Remove "token " prefix
            elif auth_header.startswith("Bearer "):
                return auth_header[7:]  # Remove "Bearer " prefix

        # Check custom JupyterHub header
        return headers.get("jupyterhub-token") or headers.get("JupyterHub-Token")

    async def is_service_available(self) -> bool:
        """Check if JupyterHub service is available."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.hub_api_url}/info", timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    return response.status == 200
        except Exception:
            return False

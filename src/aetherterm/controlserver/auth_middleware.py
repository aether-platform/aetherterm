"""AuthMiddleware -- Admin authentication for ControlServer REST API.

Supports two modes:
  1. API key authentication (header: X-API-Key)
  2. JWT bearer token authentication (header: Authorization: Bearer <token>)

Configuration via environment variables:
  CONTROL_AUTH_ENABLED=true|false  (default: false for dev)
  CONTROL_API_KEYS=key1,key2,...   (comma-separated valid API keys)
  CONTROL_JWT_SECRET=<secret>      (JWT HMAC secret)
  CONTROL_JWT_ALGORITHM=HS256      (default)
  CONTROL_JWT_ISSUER=<issuer>      (optional, validates iss claim)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from typing import Any

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

_JWT_PARTS_COUNT = 3


class AuthConfig:
    """Authentication configuration from environment variables."""

    def __init__(self) -> None:
        """Load auth configuration from environment."""
        self.enabled = os.environ.get("CONTROL_AUTH_ENABLED", "false").lower() == "true"
        self.api_keys = {
            k.strip()
            for k in os.environ.get("CONTROL_API_KEYS", "").split(",")
            if k.strip()
        }
        self.jwt_secret = os.environ.get("CONTROL_JWT_SECRET", "")
        self.jwt_algorithm = os.environ.get("CONTROL_JWT_ALGORITHM", "HS256")
        self.jwt_issuer = os.environ.get("CONTROL_JWT_ISSUER", "")

    @property
    def has_api_keys(self) -> bool:
        """Whether API keys are configured."""
        return bool(self.api_keys)

    @property
    def has_jwt(self) -> bool:
        """Whether JWT secret is configured."""
        return bool(self.jwt_secret)


_config: AuthConfig | None = None


def get_auth_config() -> AuthConfig:
    """Get or create the singleton auth config."""
    global _config  # noqa: PLW0603
    if _config is None:
        _config = AuthConfig()
    return _config


def reset_auth_config() -> None:
    """Reset config (for testing)."""
    global _config  # noqa: PLW0603
    _config = None


# FastAPI security schemes
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer_scheme = HTTPBearer(auto_error=False)


def _b64decode(s: str) -> bytes:
    """URL-safe base64 decode with padding."""
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * padding)


def _verify_jwt(token: str, config: AuthConfig) -> dict[str, Any]:
    """Verify a JWT token and return its claims.

    Uses PyJWT if available, otherwise falls back to manual HMAC verification
    of a simple base64url-encoded JSON payload (no library dependency).
    """
    try:
        import jwt as pyjwt  # noqa: PLC0415

        kwargs: dict[str, Any] = {
            "algorithms": [config.jwt_algorithm],
            "options": {},
        }
        if config.jwt_issuer:
            kwargs["issuer"] = config.jwt_issuer

        return pyjwt.decode(token, config.jwt_secret, **kwargs)

    except ImportError:
        return _verify_jwt_minimal(token, config)

    except Exception as e:
        logger.warning(f"JWT verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")


def _verify_jwt_minimal(token: str, config: AuthConfig) -> dict[str, Any]:
    """Minimal JWT verification without PyJWT dependency (HS256 only)."""
    parts = token.split(".")
    if len(parts) != _JWT_PARTS_COUNT:
        raise HTTPException(status_code=401, detail="Invalid token format")

    try:
        header = json.loads(_b64decode(parts[0]))
        payload = json.loads(_b64decode(parts[1]))

        if header.get("alg") != "HS256":
            raise HTTPException(status_code=401, detail="Unsupported algorithm")

        # Verify signature
        signing_input = f"{parts[0]}.{parts[1]}".encode()
        expected_sig = hmac.new(
            config.jwt_secret.encode(), signing_input, hashlib.sha256
        ).digest()
        actual_sig = _b64decode(parts[2])

        if not hmac.compare_digest(expected_sig, actual_sig):
            raise HTTPException(status_code=401, detail="Invalid signature")

        # Validate issuer if configured
        if config.jwt_issuer and payload.get("iss") != config.jwt_issuer:
            raise HTTPException(status_code=401, detail="Invalid issuer")

        return payload

    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Minimal JWT verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")


async def require_admin(
    request: Request,
    api_key: str | None = Security(_api_key_header),
    bearer: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
) -> dict[str, Any]:
    """FastAPI dependency that enforces admin authentication.

    Returns a dict with user info extracted from the credential.
    Skip authentication if CONTROL_AUTH_ENABLED is false (dev mode).
    """
    config = get_auth_config()

    if not config.enabled:
        return {"user": "anonymous", "auth_method": "disabled"}

    # Try API key first
    if api_key and config.has_api_keys:
        if api_key in config.api_keys:
            return {"user": "api_key_user", "auth_method": "api_key"}

    # Try JWT bearer token
    if bearer and config.has_jwt:
        claims = _verify_jwt(bearer.credentials, config)
        return {
            "user": claims.get("sub", "jwt_user"),
            "auth_method": "jwt",
            "claims": claims,
        }

    # No valid credentials provided
    if not config.has_api_keys and not config.has_jwt:
        logger.warning("Auth enabled but no API keys or JWT secret configured")
        raise HTTPException(
            status_code=500,
            detail="Authentication is enabled but not configured",
        )

    raise HTTPException(
        status_code=401,
        detail="Authentication required. Provide X-API-Key header or Bearer token.",
    )

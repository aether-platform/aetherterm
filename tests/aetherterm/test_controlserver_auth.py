"""Tests for ControlServer auth middleware."""

import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from aetherterm.controlserver.auth_middleware import (
    AuthConfig,
    _verify_jwt_minimal,
    get_auth_config,
    require_admin,
    reset_auth_config,
)


# ---------------------------------------------------------------------------
# AuthConfig tests
# ---------------------------------------------------------------------------


class TestAuthConfig:
    def test_defaults(self):
        # Clear env vars
        for key in ("CONTROL_AUTH_ENABLED", "CONTROL_API_KEYS", "CONTROL_JWT_SECRET"):
            os.environ.pop(key, None)
        reset_auth_config()

        config = AuthConfig()
        assert config.enabled is False
        assert config.has_api_keys is False
        assert config.has_jwt is False

    def test_from_env(self):
        os.environ["CONTROL_AUTH_ENABLED"] = "true"
        os.environ["CONTROL_API_KEYS"] = "key1,key2"
        os.environ["CONTROL_JWT_SECRET"] = "mysecret"
        try:
            config = AuthConfig()
            assert config.enabled is True
            assert config.has_api_keys is True
            assert "key1" in config.api_keys
            assert "key2" in config.api_keys
            assert config.has_jwt is True
            assert config.jwt_secret == "mysecret"
        finally:
            os.environ.pop("CONTROL_AUTH_ENABLED", None)
            os.environ.pop("CONTROL_API_KEYS", None)
            os.environ.pop("CONTROL_JWT_SECRET", None)
            reset_auth_config()


# ---------------------------------------------------------------------------
# require_admin tests
# ---------------------------------------------------------------------------


class TestRequireAdmin:
    @pytest.mark.asyncio
    async def test_disabled_auth(self):
        os.environ.pop("CONTROL_AUTH_ENABLED", None)
        reset_auth_config()

        result = await require_admin(
            request=MagicMock(),
            api_key=None,
            bearer=None,
        )
        assert result["auth_method"] == "disabled"
        assert result["user"] == "anonymous"

    @pytest.mark.asyncio
    async def test_api_key_valid(self):
        os.environ["CONTROL_AUTH_ENABLED"] = "true"
        os.environ["CONTROL_API_KEYS"] = "valid-key"
        reset_auth_config()

        try:
            result = await require_admin(
                request=MagicMock(),
                api_key="valid-key",
                bearer=None,
            )
            assert result["auth_method"] == "api_key"
        finally:
            os.environ.pop("CONTROL_AUTH_ENABLED", None)
            os.environ.pop("CONTROL_API_KEYS", None)
            reset_auth_config()

    @pytest.mark.asyncio
    async def test_api_key_invalid(self):
        os.environ["CONTROL_AUTH_ENABLED"] = "true"
        os.environ["CONTROL_API_KEYS"] = "valid-key"
        reset_auth_config()

        try:
            with pytest.raises(HTTPException) as exc_info:
                await require_admin(
                    request=MagicMock(),
                    api_key="wrong-key",
                    bearer=None,
                )
            assert exc_info.value.status_code == 401
        finally:
            os.environ.pop("CONTROL_AUTH_ENABLED", None)
            os.environ.pop("CONTROL_API_KEYS", None)
            reset_auth_config()

    @pytest.mark.asyncio
    async def test_no_credentials_configured(self):
        os.environ["CONTROL_AUTH_ENABLED"] = "true"
        os.environ.pop("CONTROL_API_KEYS", None)
        os.environ.pop("CONTROL_JWT_SECRET", None)
        reset_auth_config()

        try:
            with pytest.raises(HTTPException) as exc_info:
                await require_admin(
                    request=MagicMock(),
                    api_key=None,
                    bearer=None,
                )
            assert exc_info.value.status_code == 500
        finally:
            os.environ.pop("CONTROL_AUTH_ENABLED", None)
            reset_auth_config()


# ---------------------------------------------------------------------------
# JWT minimal verification tests
# ---------------------------------------------------------------------------


class TestJWTMinimal:
    def test_invalid_format(self):
        config = AuthConfig()
        config.jwt_secret = "secret"

        with pytest.raises(HTTPException) as exc_info:
            _verify_jwt_minimal("not.a.valid.jwt.token", config)
        assert exc_info.value.status_code == 401

    def test_invalid_parts_count(self):
        config = AuthConfig()
        config.jwt_secret = "secret"

        with pytest.raises(HTTPException) as exc_info:
            _verify_jwt_minimal("only-one-part", config)
        assert exc_info.value.status_code == 401

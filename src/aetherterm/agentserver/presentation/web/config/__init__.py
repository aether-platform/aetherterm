"""
Configuration module for AetherTerm server.

This module provides configuration management functionality including:
- Default configuration constants
- Environment variable parsing
- Configuration path setup
- Configuration validation
- SSL configuration utilities
"""

from .server_config import (
    DEFAULT_CONFIG,
    setup_config_paths,
    parse_environment_config,
    validate_config,
    create_server_config,
    get_ssl_paths,
    is_ssl_configured,
)

__all__ = [
    "DEFAULT_CONFIG",
    "setup_config_paths",
    "parse_environment_config",
    "validate_config",
    "create_server_config",
    "get_ssl_paths",
    "is_ssl_configured",
]

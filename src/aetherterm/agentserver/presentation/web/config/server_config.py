#!/usr/bin/env python

# This file is part of aetherterm
#
# aetherterm Copyright(C) 2015-2017 Florian Mounier
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Server Configuration Module

This module provides configuration management functionality for the AetherTerm server,
including default configuration values, path setup, environment variable parsing,
and configuration validation.
"""

import os
import shutil
from typing import Any, Dict

# Default configuration values for the AetherTerm server
DEFAULT_CONFIG = {
    "debug": False,
    "more": False,
    "unminified": False,
    "host": "localhost",
    "port": 57575,
    "keepalive_interval": 30,
    "one_shot": False,
    "shell": None,
    "motd": "motd",
    "cmd": None,
    "unsecure": False,
    "i_hereby_declare_i_dont_want_any_security_whatsoever": False,
    "login": False,
    "pam_profile": "",
    "force_unicode_width": False,
    "ssl_version": None,
    "generate_certs": False,
    "generate_current_user_pkcs": False,
    "generate_user_pkcs": "",
    "uri_root_path": "",
    "ai_mode": "streaming",  # AI assistance mode
    "ai_provider": "mock",  # AI provider (anthropic, mock)
    "ai_api_key": None,  # AI API key (will be read from env)
    "ai_model": "claude-3-5-sonnet-20241022",  # AI model
    "conf": "",  # Will be set dynamically
    "ssl_dir": "",  # Will be set dynamically
}


def setup_config_paths(config_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Setup configuration paths and update the config dictionary.

    This function determines the appropriate configuration directory based on
    user privileges and XDG Base Directory Specification, then sets up the
    configuration file and SSL directory paths.

    Args:
        config_dict: The configuration dictionary to update

    Returns:
        Dict[str, Any]: Updated configuration dictionary with paths set

    Side Effects:
        - Creates default configuration file if it doesn't exist
        - Prints installation message if config file is created
    """
    # Determine config directory based on user privileges
    if os.getuid() == 0:
        # Root user: use system-wide config directory
        ev = os.getenv("XDG_CONFIG_DIRS", "/etc")
    else:
        # Regular user: use user-specific config directory
        ev = os.getenv(
            "XDG_CONFIG_HOME",
            os.path.join(os.getenv("HOME", os.path.expanduser("~")), ".config"),
        )

    # Set up AetherTerm-specific paths
    aetherterm_dir = os.path.join(ev, "aetherterm")
    conf_file = os.path.join(aetherterm_dir, "aetherterm.conf")
    ssl_dir = os.path.join(aetherterm_dir, "ssl")

    # Update configuration dictionary
    config_dict["conf"] = conf_file
    config_dict["ssl_dir"] = ssl_dir

    # Create default configuration file if it doesn't exist
    if not os.path.exists(conf_file):
        try:
            # Ensure the directory exists
            os.makedirs(aetherterm_dir, exist_ok=True)

            # Copy default configuration file
            default_conf_path = os.path.join(
                os.path.abspath(os.path.dirname(__file__)), "..", "butterfly.conf.default"
            )
            if os.path.exists(default_conf_path):
                shutil.copy(default_conf_path, conf_file)
                print("aetherterm.conf installed in %s" % conf_file)
            else:
                print(f"Warning: Default configuration file not found at {default_conf_path}")
        except Exception as e:
            print(f"Could not install default aetherterm.conf: {e}")

    return config_dict


def parse_environment_config() -> Dict[str, Any]:
    """
    Parse configuration from environment variables.

    This function reads various AetherTerm configuration values from environment
    variables and returns them in a dictionary format suitable for merging with
    the default configuration.

    Returns:
        Dict[str, Any]: Configuration values parsed from environment variables
    """
    config = {}

    # Basic server settings
    config["host"] = os.getenv("AETHERTERM_HOST", "localhost")

    # Parse port as integer
    try:
        config["port"] = int(os.getenv("AETHERTERM_PORT", "57575"))
    except ValueError:
        config["port"] = 57575

    # Boolean flags
    config["debug"] = _parse_bool_env("AETHERTERM_DEBUG", False)
    config["more"] = _parse_bool_env("AETHERTERM_MORE", False)
    config["unsecure"] = _parse_bool_env("AETHERTERM_UNSECURE", False)
    config["login"] = _parse_bool_env("AETHERTERM_LOGIN", False)

    # String settings
    config["uri_root_path"] = os.getenv("AETHERTERM_URI_ROOT_PATH", "")
    config["pam_profile"] = os.getenv("AETHERTERM_PAM_PROFILE", "")

    # AI-related settings
    config["ai_mode"] = os.getenv("AETHERTERM_AI_MODE", "streaming")
    config["ai_provider"] = os.getenv(
        "AETHERTERM_AI_PROVIDER", "anthropic" if os.getenv("ANTHROPIC_API_KEY") else "mock"
    )
    config["ai_api_key"] = os.getenv("ANTHROPIC_API_KEY")
    config["ai_model"] = os.getenv("AETHERTERM_AI_MODEL", "claude-3-5-sonnet-20241022")

    return config


def _parse_bool_env(env_var: str, default: bool = False) -> bool:
    """
    Parse a boolean value from an environment variable.

    Args:
        env_var: Environment variable name
        default: Default value if environment variable is not set

    Returns:
        bool: Parsed boolean value
    """
    value = os.getenv(env_var, "").lower()
    return value in ("true", "1", "yes", "on")


def validate_config(config: Dict[str, Any]) -> Dict[str, str]:
    """
    Validate configuration values and return any validation errors.

    Args:
        config: Configuration dictionary to validate

    Returns:
        Dict[str, str]: Dictionary of validation errors (empty if valid)
    """
    errors = {}

    # Validate port range
    port = config.get("port", 57575)
    if not isinstance(port, int) or port < 1 or port > 65535:
        errors["port"] = f"Port must be an integer between 1 and 65535, got: {port}"

    # Validate host
    host = config.get("host", "localhost")
    if not isinstance(host, str) or not host.strip():
        errors["host"] = f"Host must be a non-empty string, got: {host}"

    # Validate AI mode
    ai_mode = config.get("ai_mode", "streaming")
    valid_ai_modes = ["streaming", "batch", "interactive"]
    if ai_mode not in valid_ai_modes:
        errors["ai_mode"] = f"AI mode must be one of {valid_ai_modes}, got: {ai_mode}"

    # Validate AI provider
    ai_provider = config.get("ai_provider", "mock")
    valid_ai_providers = ["anthropic", "mock", "openai", "lmstudio"]
    if ai_provider not in valid_ai_providers:
        errors["ai_provider"] = (
            f"AI provider must be one of {valid_ai_providers}, got: {ai_provider}"
        )

    # Validate AI API key if provider is not mock
    if ai_provider != "mock" and not config.get("ai_api_key"):
        errors["ai_api_key"] = f"AI API key is required when provider is '{ai_provider}'"

    # Validate keepalive interval
    keepalive = config.get("keepalive_interval", 30)
    if not isinstance(keepalive, int) or keepalive < 1:
        errors["keepalive_interval"] = (
            f"Keepalive interval must be a positive integer, got: {keepalive}"
        )

    return errors


def create_server_config(**kwargs) -> Dict[str, Any]:
    """
    Create a complete server configuration by merging defaults, environment variables,
    and provided keyword arguments.

    This function follows the precedence order:
    1. Default configuration (lowest priority)
    2. Environment variables
    3. Keyword arguments (highest priority)

    Args:
        **kwargs: Configuration values to override defaults and environment

    Returns:
        Dict[str, Any]: Complete server configuration

    Raises:
        ValueError: If configuration validation fails
    """
    # Start with default configuration
    config = DEFAULT_CONFIG.copy()

    # Setup configuration paths
    config = setup_config_paths(config)

    # Merge environment variables
    env_config = parse_environment_config()
    config.update(env_config)

    # Merge provided keyword arguments (highest priority)
    config.update(kwargs)

    # Validate the final configuration
    validation_errors = validate_config(config)
    if validation_errors:
        error_msg = "Configuration validation failed:\n"
        for field, error in validation_errors.items():
            error_msg += f"  - {field}: {error}\n"
        raise ValueError(error_msg)

    return config


def get_ssl_paths(config: Dict[str, Any]) -> Dict[str, str]:
    """
    Generate SSL certificate file paths based on configuration.

    Args:
        config: Server configuration dictionary

    Returns:
        Dict[str, str]: Dictionary containing SSL file paths
    """
    ssl_dir = config["ssl_dir"]
    host = config["host"]

    return {
        "ca_cert": os.path.join(ssl_dir, "aetherterm_ca.crt"),
        "ca_key": os.path.join(ssl_dir, "aetherterm_ca.key"),
        "server_cert": os.path.join(ssl_dir, f"aetherterm_{host}.crt"),
        "server_key": os.path.join(ssl_dir, f"aetherterm_{host}.key"),
        "pkcs12": os.path.join(ssl_dir, f"{host}.p12"),
    }


def is_ssl_configured(config: Dict[str, Any]) -> bool:
    """
    Check if SSL certificates are properly configured for the server.

    Args:
        config: Server configuration dictionary

    Returns:
        bool: True if SSL is properly configured, False otherwise
    """
    if config.get("unsecure", False):
        return False

    ssl_paths = get_ssl_paths(config)
    required_files = [ssl_paths["server_cert"], ssl_paths["server_key"], ssl_paths["ca_cert"]]

    return all(os.path.exists(path) for path in required_files)

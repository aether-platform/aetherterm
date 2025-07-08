"""
Validation Utilities - Infrastructure Layer

Common validation functions for data integrity, format checking, etc.
"""

import re
import json
import logging
from typing import Any, Dict, List, Optional, Union, Callable
from datetime import datetime
from urllib.parse import urlparse
from pathlib import Path

log = logging.getLogger("aetherterm.infrastructure.validation_utils")


class ValidationUtilities:
    """Centralized validation operations and utilities."""

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email address format."""
        if not email or len(email) > 254:
            return False

        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return bool(re.match(pattern, email))

    @staticmethod
    def validate_username(
        username: str, min_length: int = 3, max_length: int = 32
    ) -> Dict[str, Any]:
        """Validate username with detailed feedback."""
        issues = []

        if not username:
            issues.append("Username is required")
            return {"valid": False, "issues": issues}

        if len(username) < min_length:
            issues.append(f"Username must be at least {min_length} characters")

        if len(username) > max_length:
            issues.append(f"Username must be no more than {max_length} characters")

        if not re.match(r"^[a-zA-Z0-9_-]+$", username):
            issues.append("Username can only contain letters, numbers, underscores, and hyphens")

        if username.startswith(("_", "-")) or username.endswith(("_", "-")):
            issues.append("Username cannot start or end with underscore or hyphen")

        return {"valid": len(issues) == 0, "issues": issues, "username": username}

    @staticmethod
    def validate_json(json_string: str) -> Dict[str, Any]:
        """Validate JSON string and return parsed data or error."""
        try:
            data = json.loads(json_string)
            return {"valid": True, "data": data, "error": None}
        except json.JSONDecodeError as e:
            return {
                "valid": False,
                "data": None,
                "error": str(e),
                "line": e.lineno if hasattr(e, "lineno") else None,
                "column": e.colno if hasattr(e, "colno") else None,
            }

    @staticmethod
    def validate_port_number(port: Union[str, int]) -> bool:
        """Validate port number is in valid range."""
        try:
            port_num = int(port)
            return 1 <= port_num <= 65535
        except (ValueError, TypeError):
            return False

    @staticmethod
    def validate_file_path(
        path: str, must_exist: bool = False, must_be_file: bool = False
    ) -> Dict[str, Any]:
        """Validate file path with various checks."""
        try:
            path_obj = Path(path)

            issues = []

            # Check for path traversal attempts
            if ".." in path or path.startswith("/"):
                if not path.startswith("/mnt/c/workspace"):  # Allow workspace paths
                    issues.append("Path contains potentially dangerous patterns")

            # Check if path exists
            if must_exist and not path_obj.exists():
                issues.append("Path does not exist")

            # Check if it's a file when required
            if must_be_file and path_obj.exists() and not path_obj.is_file():
                issues.append("Path exists but is not a file")

            # Check if path is too long
            if len(path) > 4096:  # Most filesystems limit
                issues.append("Path is too long")

            return {
                "valid": len(issues) == 0,
                "issues": issues,
                "path": str(path_obj),
                "exists": path_obj.exists() if path_obj else False,
                "is_file": path_obj.is_file() if path_obj.exists() else None,
                "is_dir": path_obj.is_dir() if path_obj.exists() else None,
            }

        except Exception as e:
            return {"valid": False, "issues": [f"Invalid path: {str(e)}"], "path": path}

    @staticmethod
    def validate_url(url: str, allowed_schemes: List[str] = None) -> Dict[str, Any]:
        """Validate URL format and components."""
        if allowed_schemes is None:
            allowed_schemes = ["http", "https"]

        try:
            parsed = urlparse(url)
            issues = []

            if not parsed.scheme:
                issues.append("URL missing scheme (http/https)")
            elif parsed.scheme not in allowed_schemes:
                issues.append(
                    f"URL scheme '{parsed.scheme}' not allowed. Allowed: {allowed_schemes}"
                )

            if not parsed.netloc:
                issues.append("URL missing domain")

            # Check for dangerous characters
            dangerous_chars = ["<", ">", '"', " "]
            if any(char in url for char in dangerous_chars):
                issues.append("URL contains dangerous characters")

            return {
                "valid": len(issues) == 0,
                "issues": issues,
                "url": url,
                "parsed": {
                    "scheme": parsed.scheme,
                    "netloc": parsed.netloc,
                    "path": parsed.path,
                    "params": parsed.params,
                    "query": parsed.query,
                    "fragment": parsed.fragment,
                },
            }

        except Exception as e:
            return {"valid": False, "issues": [f"Invalid URL format: {str(e)}"], "url": url}

    @staticmethod
    def validate_datetime(
        date_string: str, format_string: str = "%Y-%m-%d %H:%M:%S"
    ) -> Dict[str, Any]:
        """Validate datetime string format."""
        try:
            parsed_date = datetime.strptime(date_string, format_string)
            return {
                "valid": True,
                "datetime": parsed_date,
                "iso_format": parsed_date.isoformat(),
                "timestamp": parsed_date.timestamp(),
            }
        except ValueError as e:
            return {
                "valid": False,
                "error": str(e),
                "input": date_string,
                "expected_format": format_string,
            }

    @staticmethod
    def validate_uuid(uuid_string: str, version: Optional[int] = None) -> Dict[str, Any]:
        """Validate UUID format."""
        import uuid

        try:
            parsed_uuid = uuid.UUID(uuid_string)

            issues = []
            if version is not None and parsed_uuid.version != version:
                issues.append(f"Expected UUID version {version}, got {parsed_uuid.version}")

            return {
                "valid": len(issues) == 0,
                "issues": issues,
                "uuid": str(parsed_uuid),
                "version": parsed_uuid.version,
                "hex": parsed_uuid.hex,
            }

        except ValueError as e:
            return {
                "valid": False,
                "issues": [f"Invalid UUID format: {str(e)}"],
                "input": uuid_string,
            }

    @staticmethod
    def validate_command(command: str, allowed_commands: List[str] = None) -> Dict[str, Any]:
        """Validate shell command for safety."""
        if not command or not command.strip():
            return {"valid": False, "issues": ["Command is empty"], "command": command}

        issues = []
        command_parts = command.strip().split()
        base_command = command_parts[0] if command_parts else ""

        # Check against allowed commands if provided
        if allowed_commands is not None:
            if base_command not in allowed_commands:
                issues.append(f"Command '{base_command}' not in allowed list")

        # Check for dangerous patterns
        dangerous_patterns = [
            r"rm\s+-rf\s+/",  # Dangerous rm commands
            r">\s*/dev/",  # Writing to device files
            r"curl.*\|\s*sh",  # Piping downloads to shell
            r"wget.*\|\s*sh",
            r"eval\s*\(",
            r"exec\s*\(",
            r"system\s*\(",
            r"`.*`",  # Command substitution
            r"\$\(",  # Command substitution
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                issues.append(f"Command contains dangerous pattern: {pattern}")

        # Check for command injection attempts
        injection_chars = [";", "|", "&", "$(", "`"]
        if any(char in command for char in injection_chars):
            # Allow some safe uses
            if not (command.count("|") == 1 and "grep" in command):  # Allow simple pipes to grep
                issues.append("Command contains potential injection characters")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "command": command,
            "base_command": base_command,
            "arguments": command_parts[1:] if len(command_parts) > 1 else [],
        }

    @staticmethod
    def validate_data_structure(
        data: Any, schema: Dict[str, Any], strict: bool = False
    ) -> Dict[str, Any]:
        """Validate data against a simple schema."""
        issues = []

        def validate_field(value: Any, field_schema: Dict[str, Any], field_name: str):
            field_issues = []

            # Check type
            expected_type = field_schema.get("type")
            if expected_type:
                if expected_type == "string" and not isinstance(value, str):
                    field_issues.append(f"{field_name} should be a string")
                elif expected_type == "integer" and not isinstance(value, int):
                    field_issues.append(f"{field_name} should be an integer")
                elif expected_type == "boolean" and not isinstance(value, bool):
                    field_issues.append(f"{field_name} should be a boolean")
                elif expected_type == "list" and not isinstance(value, list):
                    field_issues.append(f"{field_name} should be a list")
                elif expected_type == "dict" and not isinstance(value, dict):
                    field_issues.append(f"{field_name} should be a dictionary")

            # Check required
            if field_schema.get("required", False) and value is None:
                field_issues.append(f"{field_name} is required")

            # Check min/max for strings and numbers
            if isinstance(value, str):
                min_length = field_schema.get("min_length")
                max_length = field_schema.get("max_length")
                if min_length and len(value) < min_length:
                    field_issues.append(f"{field_name} must be at least {min_length} characters")
                if max_length and len(value) > max_length:
                    field_issues.append(
                        f"{field_name} must be no more than {max_length} characters"
                    )

            # Check custom validator
            validator = field_schema.get("validator")
            if validator and callable(validator):
                try:
                    if not validator(value):
                        field_issues.append(f"{field_name} failed custom validation")
                except Exception as e:
                    field_issues.append(f"{field_name} validation error: {str(e)}")

            return field_issues

        # Validate top-level structure
        if not isinstance(data, dict):
            return {"valid": False, "issues": ["Data must be a dictionary"], "data": data}

        # Check each field in schema
        for field_name, field_schema in schema.items():
            value = data.get(field_name)
            field_issues = validate_field(value, field_schema, field_name)
            issues.extend(field_issues)

        # In strict mode, check for extra fields
        if strict:
            extra_fields = set(data.keys()) - set(schema.keys())
            if extra_fields:
                issues.append(f"Unexpected fields: {', '.join(extra_fields)}")

        return {"valid": len(issues) == 0, "issues": issues, "data": data}

    @staticmethod
    def sanitize_input(input_string: str, max_length: int = 1000) -> str:
        """Sanitize input string by removing/escaping dangerous content."""
        if not input_string:
            return ""

        # Truncate if too long
        if len(input_string) > max_length:
            input_string = input_string[:max_length]

        # Remove null bytes
        input_string = input_string.replace("\x00", "")

        # Replace dangerous HTML/XML characters
        replacements = {"<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#x27;", "&": "&amp;"}

        for char, replacement in replacements.items():
            input_string = input_string.replace(char, replacement)

        return input_string

"""
Security Utilities - Infrastructure Layer

Common security operations and utilities for authentication, validation, encryption, etc.
"""

import hashlib
import secrets
import hmac
import base64
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from pathlib import Path
import re

log = logging.getLogger("aetherterm.infrastructure.security_utils")


class SecurityUtilities:
    """Centralized security operations and utilities."""

    @staticmethod
    def generate_secure_token(length: int = 32) -> str:
        """Generate a cryptographically secure random token."""
        return secrets.token_urlsafe(length)

    @staticmethod
    def generate_session_id() -> str:
        """Generate a secure session ID."""
        return f"session_{secrets.token_urlsafe(16)}_{int(datetime.now().timestamp())}"

    @staticmethod
    def hash_password(password: str, salt: Optional[str] = None) -> Dict[str, str]:
        """Hash a password with salt using PBKDF2."""
        if salt is None:
            salt = secrets.token_hex(16)

        # Use PBKDF2 with SHA-256
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
        hashed = base64.b64encode(key).decode("utf-8")

        return {"hash": hashed, "salt": salt, "algorithm": "pbkdf2_sha256", "iterations": 100000}

    @staticmethod
    def verify_password(password: str, password_data: Dict[str, str]) -> bool:
        """Verify a password against stored hash data."""
        try:
            expected_hash = SecurityUtilities.hash_password(password, password_data["salt"])
            return hmac.compare_digest(expected_hash["hash"], password_data["hash"])
        except Exception as e:
            log.error(f"Failed to verify password: {e}")
            return False

    @staticmethod
    def validate_input_safe(input_string: str, max_length: int = 1000) -> bool:
        """Validate that input string is safe (no obvious injection attempts)."""
        if not input_string or len(input_string) > max_length:
            return False

        # Check for common injection patterns
        dangerous_patterns = [
            r"<script.*?>",
            r"javascript:",
            r"vbscript:",
            r"on\w+\s*=",
            r"eval\s*\(",
            r"exec\s*\(",
            r"system\s*\(",
            r"\/\*.*?\*\/",
            r"--",
            r";.*drop",
            r";.*delete",
            r";.*insert",
            r";.*update",
            r"union.*select",
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, input_string, re.IGNORECASE):
                log.warning(f"Potentially dangerous input detected: {pattern}")
                return False

        return True

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename to prevent directory traversal and other attacks."""
        # Remove path separators and other dangerous characters
        filename = re.sub(r'[<>:"/\\|?*]', "", filename)
        filename = re.sub(r"\.\.", "", filename)  # Remove .. sequences
        filename = filename.strip(". ")  # Remove leading/trailing dots and spaces

        # Limit length
        if len(filename) > 255:
            name, ext = Path(filename).stem, Path(filename).suffix
            filename = name[: 255 - len(ext)] + ext

        # Ensure it's not empty after sanitization
        if not filename:
            filename = f"file_{secrets.token_hex(4)}"

        return filename

    @staticmethod
    def validate_url_safe(url: str) -> bool:
        """Validate that URL is safe (no obvious attacks)."""
        if not url:
            return False

        # Check for dangerous protocols
        dangerous_protocols = ["javascript:", "vbscript:", "data:", "file:"]
        url_lower = url.lower()

        for protocol in dangerous_protocols:
            if url_lower.startswith(protocol):
                return False

        # Check for obvious injection attempts
        if not SecurityUtilities.validate_input_safe(url):
            return False

        return True

    @staticmethod
    def generate_csrf_token() -> str:
        """Generate a CSRF token."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def create_hmac_signature(message: str, secret_key: str) -> str:
        """Create HMAC signature for message integrity."""
        signature = hmac.new(
            secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return signature

    @staticmethod
    def verify_hmac_signature(message: str, signature: str, secret_key: str) -> bool:
        """Verify HMAC signature."""
        try:
            expected_signature = SecurityUtilities.create_hmac_signature(message, secret_key)
            return hmac.compare_digest(signature, expected_signature)
        except Exception as e:
            log.error(f"Failed to verify HMAC signature: {e}")
            return False

    @staticmethod
    def check_password_strength(password: str) -> Dict[str, Any]:
        """Check password strength and return detailed feedback."""
        score = 0
        feedback = []
        requirements = {
            "min_length": len(password) >= 8,
            "has_lowercase": bool(re.search(r"[a-z]", password)),
            "has_uppercase": bool(re.search(r"[A-Z]", password)),
            "has_digits": bool(re.search(r"\d", password)),
            "has_special": bool(re.search(r'[!@#$%^&*(),.?":{}|<>]', password)),
            "no_common_patterns": not bool(
                re.search(r"(123|abc|password|qwerty)", password, re.IGNORECASE)
            ),
        }

        for req, met in requirements.items():
            if met:
                score += 1
            else:
                if req == "min_length":
                    feedback.append("Password should be at least 8 characters long")
                elif req == "has_lowercase":
                    feedback.append("Add lowercase letters")
                elif req == "has_uppercase":
                    feedback.append("Add uppercase letters")
                elif req == "has_digits":
                    feedback.append("Add numbers")
                elif req == "has_special":
                    feedback.append("Add special characters")
                elif req == "no_common_patterns":
                    feedback.append("Avoid common patterns like '123' or 'password'")

        strength_levels = ["Very Weak", "Weak", "Fair", "Good", "Strong", "Very Strong"]
        strength = strength_levels[min(score, len(strength_levels) - 1)]

        return {
            "score": score,
            "max_score": len(requirements),
            "strength": strength,
            "requirements_met": requirements,
            "feedback": feedback,
            "is_strong": score >= 4,
        }

    @staticmethod
    def mask_sensitive_data(data: str, mask_char: str = "*", visible_chars: int = 4) -> str:
        """Mask sensitive data like API keys, passwords, etc."""
        if not data or len(data) <= visible_chars:
            return mask_char * 8  # Standard masked length

        visible_start = data[: visible_chars // 2] if visible_chars > 0 else ""
        visible_end = data[-(visible_chars // 2) :] if visible_chars > 0 else ""
        masked_middle = mask_char * max(8, len(data) - visible_chars)

        return visible_start + masked_middle + visible_end

    @staticmethod
    def get_client_ip_from_headers(headers: Dict[str, str]) -> Optional[str]:
        """Extract client IP from request headers, considering proxies."""
        # Check common proxy headers in order of preference
        ip_headers = [
            "X-Forwarded-For",
            "X-Real-IP",
            "X-Client-IP",
            "CF-Connecting-IP",  # Cloudflare
            "True-Client-IP",
            "X-Forwarded",
            "Forwarded",
        ]

        for header in ip_headers:
            if header in headers:
                ip = headers[header].split(",")[0].strip()
                if SecurityUtilities.is_valid_ip(ip):
                    return ip

        return None

    @staticmethod
    def is_valid_ip(ip: str) -> bool:
        """Validate if string is a valid IP address."""
        try:
            import ipaddress

            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False

    @staticmethod
    def rate_limit_key(identifier: str, action: str, window: str = "1h") -> str:
        """Generate rate limiting key."""
        return f"rate_limit:{action}:{identifier}:{window}"

    @staticmethod
    def is_safe_redirect_url(url: str, allowed_domains: List[str] = None) -> bool:
        """Check if redirect URL is safe."""
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)

            # Relative URLs are generally safe
            if not parsed.netloc:
                return True

            # Check against allowed domains if provided
            if allowed_domains:
                return any(parsed.netloc.endswith(domain) for domain in allowed_domains)

            # Default: only allow HTTPS for external redirects
            return parsed.scheme == "https"

        except Exception:
            return False

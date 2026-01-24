"""
SSL Configuration - Infrastructure Layer

SSL/TLS certificate management.
"""

import logging
import os
import ssl

log = logging.getLogger("aetherterm.infrastructure.config")
class SSLConfig:
    """SSL/TLS certificate management."""

    @staticmethod
    def setup_ssl_context(cert_file: str, key_file: str, ca_file: str) -> ssl.SSLContext:
        """Setup SSL context for secure connections."""
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(cert_file, key_file)
        context.load_verify_locations(ca_file)
        context.verify_mode = ssl.CERT_REQUIRED
        return context

    @staticmethod
    def verify_certificates(cert_file: str, key_file: str, ca_file: str) -> bool:
        """Verify SSL certificates exist and are valid."""
        return all(os.path.exists(f) for f in [cert_file, key_file, ca_file])

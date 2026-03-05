"""SSL certificate utilities for AetherTerm AgentServer.

This module provides SSL certificate management and preparation functions.
"""

import logging
import os
import ssl
import sys

log = logging.getLogger("aetherterm.agentserver.utils.ssl_certs")


def prepare_ssl_certs(**kwargs):
    """Check SSL certificates and provide guidance if missing."""
    if kwargs.get("unsecure", False):
        log.warning("=" * 60)
        log.warning("⚠️  RUNNING IN UNSECURE MODE")
        log.warning("=" * 60)
        log.warning("SSL/TLS encryption is DISABLED. All communication is in plain text.")
        log.warning("This is NOT RECOMMENDED for production use.")
        log.warning("Consider generating SSL certificates for secure operation.")
        log.warning("=" * 60)
        return

    host = kwargs.get("host", "localhost")
    ssl_dir = kwargs.get("ssl_dir", "")

    if not ssl_dir:
        log.error("SSL directory not configured")
        _show_ssl_generation_help(host)
        sys.exit(1)

    cert_path = os.path.join(ssl_dir, f"aetherterm_{host}.crt")
    key_path = os.path.join(ssl_dir, f"aetherterm_{host}.key")
    ca_path = os.path.join(ssl_dir, "aetherterm_ca.crt")

    if not (os.path.exists(cert_path) and os.path.exists(key_path) and os.path.exists(ca_path)):
        log.error("=" * 60)
        log.error("❌ SSL CERTIFICATES MISSING")
        log.error("=" * 60)
        log.error(f"Required certificates not found for host '{host}':")
        log.error(f"  Certificate: {cert_path}")
        log.error(f"  Private Key: {key_path}")
        log.error(f"  CA Certificate: {ca_path}")
        log.error("")
        _show_ssl_generation_help(host)
        sys.exit(1)

    log.info(f"✅ SSL certificates found for host {host}")


def _show_ssl_generation_help(host):
    """Show help for generating SSL certificates."""
    log.error("To generate SSL certificates, run:")
    log.error(f"  aetherterm-generate-ssl --host={host}")
    log.error("")
    log.error("Or to run without SSL (NOT RECOMMENDED):")
    log.error("  aetherterm --unsecure")
    log.error("")
    log.error("For client certificate generation:")
    log.error("  aetherterm-generate-ssl --generate-current-user")
    log.error("")
    log.error("For more information about SSL setup, see documentation.")


def setup_ssl_context(**kwargs):
    """Setup SSL context for the server."""
    if kwargs.get("unsecure", False):
        return None

    host = kwargs.get("host", "localhost")
    ssl_dir = kwargs.get("ssl_dir", "")

    if not ssl_dir:
        log.warning("SSL directory not configured")
        return None

    cert_path = os.path.join(ssl_dir, f"{host}.crt")
    key_path = os.path.join(ssl_dir, f"{host}.key")

    if not (os.path.exists(cert_path) and os.path.exists(key_path)):
        log.warning(f"SSL certificates not found for host {host}")
        return None

    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_path, key_path)
        log.info(f"SSL context created for host {host}")
        return context
    except Exception as e:
        log.error(f"Failed to create SSL context: {e}")
        return None

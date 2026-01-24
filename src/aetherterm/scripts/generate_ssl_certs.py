#!/usr/bin/env python
"""
SSL Certificate Generation Script for AetherTerm
"""

import getpass
import logging
import os
import socket
import sys
import uuid
from pathlib import Path

import click

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("aetherterm.ssl_generator")
def get_ssl_directory():
    """Get the default SSL directory."""
    if os.getuid() == 0:
        config_dir = os.getenv("XDG_CONFIG_DIRS", "/etc")
    else:
        config_dir = os.getenv(
            "XDG_CONFIG_HOME",
            os.path.join(os.getenv("HOME", os.path.expanduser("~")), ".config"),
        )
    return os.path.join(config_dir, "aetherterm", "ssl")
def ensure_directory_exists(path):
    """Ensure directory exists and has proper permissions."""
    Path(path).mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)  # Only owner can read/write/execute
def write_file(file_path, content, mode=0o600):
    """Write content to file with specific permissions."""
    with open(file_path, "wb") as fd:
        fd.write(content)
    os.chmod(file_path, mode)
    log.info(f"Created: {file_path}")
def read_file(file_path):
    """Read file content."""
    with open(file_path, "rb") as fd:
        return fd.read()
def fill_certificate_fields(subject):
    """Fill standard certificate fields."""
    subject.C = "WW"
    subject.O = "AetherTerm"
    subject.OU = "AetherTerm Terminal"
    subject.ST = "World Wide"
    subject.L = "Terminal"
def generate_ca_certificate(ssl_dir):
    """Generate Certificate Authority certificate."""
    try:
        from OpenSSL import crypto
    except ImportError:
        log.error("OpenSSL library is required for certificate generation")
        log.error("Install with: pip install pyOpenSSL")
        sys.exit(1)

    ca_cert_path = os.path.join(ssl_dir, "aetherterm_ca.crt")
    ca_key_path = os.path.join(ssl_dir, "aetherterm_ca.key")

    if os.path.exists(ca_cert_path) and os.path.exists(ca_key_path):
        log.info("Root CA certificate already exists, using existing one")
        return crypto.load_certificate(
            crypto.FILETYPE_PEM, read_file(ca_cert_path)
        ), crypto.load_privatekey(crypto.FILETYPE_PEM, read_file(ca_key_path))

    log.info("Generating Root CA certificate...")

    # Generate CA private key
    ca_key = crypto.PKey()
    ca_key.generate_key(crypto.TYPE_RSA, 2048)

    # Generate CA certificate
    ca_cert = crypto.X509()
    ca_cert.set_version(2)
    ca_cert.get_subject().CN = f"AetherTerm CA on {socket.gethostname()}"
    fill_certificate_fields(ca_cert.get_subject())
    ca_cert.set_serial_number(uuid.uuid4().int)
    ca_cert.gmtime_adj_notBefore(0)  # Valid from now
    ca_cert.gmtime_adj_notAfter(315360000)  # Valid for 10 years
    ca_cert.set_issuer(ca_cert.get_subject())  # Self-signed
    ca_cert.set_pubkey(ca_key)

    # Add CA extensions
    ca_cert.add_extensions(
        [
            crypto.X509Extension(b"basicConstraints", True, b"CA:TRUE, pathlen:0"),
            crypto.X509Extension(b"keyUsage", True, b"keyCertSign, cRLSign"),
            crypto.X509Extension(b"subjectKeyIdentifier", False, b"hash", subject=ca_cert),
        ]
    )
    ca_cert.add_extensions(
        [
            crypto.X509Extension(
                b"authorityKeyIdentifier",
                False,
                b"issuer:always, keyid:always",
                issuer=ca_cert,
                subject=ca_cert,
            )
        ]
    )

    # Sign the certificate
    ca_cert.sign(ca_key, "sha256")

    # Write CA certificate and key
    write_file(ca_cert_path, crypto.dump_certificate(crypto.FILETYPE_PEM, ca_cert))
    write_file(ca_key_path, crypto.dump_privatekey(crypto.FILETYPE_PEM, ca_key), 0o600)

    return ca_cert, ca_key
def generate_server_certificate(ssl_dir, host, ca_cert, ca_key):
    """Generate server certificate signed by CA."""
    try:
        from OpenSSL import crypto
    except ImportError:
        log.error("OpenSSL library is required for certificate generation")
        sys.exit(1)

    server_cert_path = os.path.join(ssl_dir, f"aetherterm_{host}.crt")
    server_key_path = os.path.join(ssl_dir, f"aetherterm_{host}.key")

    log.info(f"Generating server certificate for host: {host}")

    # Generate server private key
    server_key = crypto.PKey()
    server_key.generate_key(crypto.TYPE_RSA, 2048)

    # Generate server certificate
    server_cert = crypto.X509()
    server_cert.set_version(2)
    server_cert.get_subject().CN = host
    fill_certificate_fields(server_cert.get_subject())
    server_cert.set_serial_number(uuid.uuid4().int)
    server_cert.gmtime_adj_notBefore(0)  # Valid from now
    server_cert.gmtime_adj_notAfter(315360000)  # Valid for 10 years
    server_cert.set_issuer(ca_cert.get_subject())  # Signed by CA
    server_cert.set_pubkey(server_key)

    # Add server certificate extensions
    server_cert.add_extensions(
        [
            crypto.X509Extension(b"basicConstraints", False, b"CA:FALSE"),
            crypto.X509Extension(b"subjectKeyIdentifier", False, b"hash", subject=server_cert),
            crypto.X509Extension(b"subjectAltName", False, f"DNS:{host}".encode()),
        ]
    )
    server_cert.add_extensions(
        [
            crypto.X509Extension(
                b"authorityKeyIdentifier",
                False,
                b"issuer:always, keyid:always",
                issuer=ca_cert,
                subject=ca_cert,
            )
        ]
    )

    # Sign with CA
    server_cert.sign(ca_key, "sha256")

    # Write server certificate and key
    write_file(server_cert_path, crypto.dump_certificate(crypto.FILETYPE_PEM, server_cert))
    write_file(server_key_path, crypto.dump_privatekey(crypto.FILETYPE_PEM, server_key), 0o600)

    return server_cert, server_key
def generate_client_certificate(ssl_dir, username, ca_cert, ca_key):
    """Generate client certificate for user authentication."""
    try:
        from OpenSSL import crypto
    except ImportError:
        log.error("OpenSSL library is required for certificate generation")
        sys.exit(1)

    log.info(f"Generating client certificate for user: {username}")

    # Generate client private key
    client_key = crypto.PKey()
    client_key.generate_key(crypto.TYPE_RSA, 2048)

    # Generate client certificate
    client_cert = crypto.X509()
    client_cert.set_version(2)
    client_cert.get_subject().CN = username
    fill_certificate_fields(client_cert.get_subject())
    client_cert.set_serial_number(uuid.uuid4().int)
    client_cert.gmtime_adj_notBefore(0)  # Valid from now
    client_cert.gmtime_adj_notAfter(315360000)  # Valid for 10 years
    client_cert.set_issuer(ca_cert.get_subject())  # Signed by CA
    client_cert.set_pubkey(client_key)

    # Sign with CA
    client_cert.sign(ca_key, "sha256")

    # Create PKCS12 bundle
    p12 = crypto.PKCS12()
    p12.set_certificate(client_cert)
    p12.set_privatekey(client_key)
    p12.set_ca_certificates([ca_cert])
    p12.set_friendlyname(f"{username} cert for AetherTerm".encode())

    # Get password for PKCS12
    while True:
        password = getpass.getpass(f"PKCS12 Password for {username} (can be blank): ")
        password2 = getpass.getpass("Verify Password: ")
        if password == password2:
            break
        print("Passwords do not match.")

    # Write PKCS12 bundle
    p12_path = os.path.join(ssl_dir, f"{username}.p12")
    write_file(p12_path, p12.export(password.encode("utf-8")), 0o600)

    return client_cert, client_key
@click.command()
@click.option("--host", default="localhost", help="Hostname for server certificate")
@click.option("--ssl-dir", help="SSL directory (default: ~/.config/aetherterm/ssl)")
@click.option("--generate-client", help="Generate client certificate for specified user")
@click.option(
    "--generate-current-user", is_flag=True, help="Generate client certificate for current user"
)
def main(host, ssl_dir, generate_client, generate_current_user):
    """Generate SSL certificates for AetherTerm."""

    # Set SSL directory
    if not ssl_dir:
        ssl_dir = get_ssl_directory()

    log.info(f"Using SSL directory: {ssl_dir}")
    ensure_directory_exists(ssl_dir)

    try:
        # Generate CA certificate
        ca_cert, ca_key = generate_ca_certificate(ssl_dir)

        # Generate server certificate
        generate_server_certificate(ssl_dir, host, ca_cert, ca_key)

        # Generate client certificate if requested
        if generate_current_user:
            import pwd

            username = pwd.getpwuid(os.getuid()).pw_name
            generate_client_certificate(ssl_dir, username, ca_cert, ca_key)
        elif generate_client:
            # Check if running as root when generating for another user
            if generate_client != pwd.getpwuid(os.getuid()).pw_name and os.getuid() != 0:
                log.error("Cannot create certificate for another user without root privileges")
                sys.exit(1)
            generate_client_certificate(ssl_dir, generate_client, ca_cert, ca_key)

        log.info("")
        log.info("🎉 SSL Certificate generation completed!")
        log.info(f"📁 Certificates stored in: {ssl_dir}")
        log.info("")
        log.info("You can now start AetherTerm with SSL enabled:")
        log.info(f"  aetherterm --host={host}")

        if generate_client or generate_current_user:
            log.info("")
            log.info("Client certificate can be imported into your browser for authentication.")

    except Exception as e:
        log.error(f"Certificate generation failed: {e}")
        sys.exit(1)
if __name__ == "__main__":
    main()

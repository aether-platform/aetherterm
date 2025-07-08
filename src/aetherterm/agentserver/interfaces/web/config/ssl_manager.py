"""
SSL/Certificate Management Module - Web Interface Layer

Handles SSL certificate generation, validation, and server configuration.
Implements Clean Architecture principles with separation of concerns.
"""

import getpass
import logging
import os
import socket
import ssl
import stat
import sys
import uuid
from typing import Dict, Tuple, Optional

log = logging.getLogger("aetherterm.interfaces.web.ssl_manager")


class SSLCertificateManager:
    """Manages SSL certificate generation, validation, and configuration."""

    def __init__(self, ssl_dir: str, host: str):
        """Initialize SSL manager with directory and host configuration."""
        self.ssl_dir = ssl_dir
        self.host = host
        self._ensure_ssl_dir()

    def _ensure_ssl_dir(self) -> None:
        """Ensure SSL directory exists."""
        if not os.path.exists(self.ssl_dir):
            os.makedirs(self.ssl_dir)

    def _to_abs(self, filename: str) -> str:
        """Convert filename to absolute path in SSL directory."""
        return os.path.join(self.ssl_dir, filename)

    def get_certificate_paths(self) -> Dict[str, str]:
        """Get paths for all certificate files."""
        return {
            "ca": self._to_abs("aetherterm_ca.crt"),
            "ca_key": self._to_abs("aetherterm_ca.key"),
            "cert": self._to_abs(f"aetherterm_{self.host}.crt"),
            "cert_key": self._to_abs(f"aetherterm_{self.host}.key"),
            "pkcs12_template": self._to_abs("{}.p12"),
        }

    def validate_server_certificates(self) -> bool:
        """Validate that all required server certificates exist."""
        paths = self.get_certificate_paths()
        required_files = [paths["cert"], paths["cert_key"], paths["ca"]]
        return all(os.path.exists(path) for path in required_files)

    def generate_ca_certificate(self) -> Tuple[object, object]:
        """Generate CA certificate and private key."""
        from OpenSSL import crypto

        paths = self.get_certificate_paths()

        if os.path.exists(paths["ca"]) and os.path.exists(paths["ca_key"]):
            log.info("Root certificate found, using existing")
            ca_cert = crypto.load_certificate(crypto.FILETYPE_PEM, self._read_file(paths["ca"]))
            ca_pk = crypto.load_privatekey(crypto.FILETYPE_PEM, self._read_file(paths["ca_key"]))
            return ca_cert, ca_pk

        log.info("Root certificate not found, generating new")

        # Generate CA private key
        ca_pk = crypto.PKey()
        ca_pk.generate_key(crypto.TYPE_RSA, 2048)

        # Generate CA certificate
        ca_cert = crypto.X509()
        ca_cert.set_version(2)
        ca_cert.get_subject().CN = f"Butterfly CA on {socket.gethostname()}"
        self._fill_certificate_fields(ca_cert.get_subject())
        ca_cert.set_serial_number(uuid.uuid4().int)
        ca_cert.gmtime_adj_notBefore(0)  # From now
        ca_cert.gmtime_adj_notAfter(315360000)  # to 10y
        ca_cert.set_issuer(ca_cert.get_subject())  # Self signed
        ca_cert.set_pubkey(ca_pk)

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
        ca_cert.sign(ca_pk, "sha512")

        # Write CA files
        self._write_file(paths["ca"], crypto.dump_certificate(crypto.FILETYPE_PEM, ca_cert))
        self._write_file(paths["ca_key"], crypto.dump_privatekey(crypto.FILETYPE_PEM, ca_pk))
        os.chmod(paths["ca_key"], stat.S_IRUSR | stat.S_IWUSR)  # 0o600 perms

        return ca_cert, ca_pk

    def generate_server_certificate(self, ca_cert: object, ca_pk: object) -> None:
        """Generate server certificate signed by CA."""
        from OpenSSL import crypto

        paths = self.get_certificate_paths()

        # Generate server private key
        server_pk = crypto.PKey()
        server_pk.generate_key(crypto.TYPE_RSA, 2048)

        # Generate server certificate
        server_cert = crypto.X509()
        server_cert.set_version(2)
        server_cert.get_subject().CN = self.host
        server_cert.add_extensions(
            [
                crypto.X509Extension(b"basicConstraints", False, b"CA:FALSE"),
                crypto.X509Extension(b"subjectKeyIdentifier", False, b"hash", subject=server_cert),
                crypto.X509Extension(b"subjectAltName", False, f"DNS:{self.host}".encode()),
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

        self._fill_certificate_fields(server_cert.get_subject())
        server_cert.set_serial_number(uuid.uuid4().int)
        server_cert.gmtime_adj_notBefore(0)  # From now
        server_cert.gmtime_adj_notAfter(315360000)  # to 10y
        server_cert.set_issuer(ca_cert.get_subject())  # Signed by ca
        server_cert.set_pubkey(server_pk)
        server_cert.sign(ca_pk, "sha512")

        # Write server files
        self._write_file(paths["cert"], crypto.dump_certificate(crypto.FILETYPE_PEM, server_cert))
        self._write_file(paths["cert_key"], crypto.dump_privatekey(crypto.FILETYPE_PEM, server_pk))
        os.chmod(paths["cert_key"], stat.S_IRUSR | stat.S_IWUSR)  # 0o600 perms

    def generate_user_certificate(self, username: str, ca_cert: object, ca_pk: object) -> None:
        """Generate user certificate for client authentication."""
        from OpenSSL import crypto

        paths = self.get_certificate_paths()

        # Generate client private key
        client_pk = crypto.PKey()
        client_pk.generate_key(crypto.TYPE_RSA, 2048)

        # Generate client certificate
        client_cert = crypto.X509()
        client_cert.set_version(2)
        client_cert.get_subject().CN = username
        self._fill_certificate_fields(client_cert.get_subject())
        client_cert.set_serial_number(uuid.uuid4().int)
        client_cert.gmtime_adj_notBefore(0)  # From now
        client_cert.gmtime_adj_notAfter(315360000)  # to 10y
        client_cert.set_issuer(ca_cert.get_subject())  # Signed by ca
        client_cert.set_pubkey(client_pk)
        client_cert.sign(client_pk, "sha512")
        client_cert.sign(ca_pk, "sha512")

        # Create PKCS12 package
        pfx = crypto.PKCS12()
        pfx.set_certificate(client_cert)
        pfx.set_privatekey(client_pk)
        pfx.set_ca_certificates([ca_cert])
        pfx.set_friendlyname(f"{username} cert for aetherterm".encode("utf-8"))

        # Get password for PKCS12
        password = self._get_pkcs12_password()

        # Write PKCS12 file
        pkcs12_path = paths["pkcs12_template"].format(username)
        self._write_file(pkcs12_path, pfx.export(password.encode("utf-8")))
        os.chmod(pkcs12_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600 perms

    def create_ssl_args(self, ssl_version: Optional[str] = None) -> Dict[str, object]:
        """Create SSL arguments for uvicorn server configuration."""
        paths = self.get_certificate_paths()

        if not self.validate_server_certificates():
            log.error("Unable to find aetherterm certificate for host %s", self.host)
            log.error("Certificate: %s", paths["cert"])
            log.error("Private key: %s", paths["cert_key"])
            log.error("CA certificate: %s", paths["ca"])
            log.error("Can't run aetherterm without certificate.")
            log.error("Either generate them using --generate-certs --host=%s", self.host)
            log.error("or run as --unsecure (NOT RECOMMENDED)")
            log.error(
                "For more information go to http://paradoxxxzero.github.io/2014/03/21/aetherterm-with-ssl-auth.html"
            )
            sys.exit(1)

        ssl_args = {
            "ssl_certfile": paths["cert"],
            "ssl_keyfile": paths["cert_key"],
            "ssl_ca_certs": paths["ca"],
            "ssl_cert_reqs": ssl.CERT_REQUIRED,
        }

        if ssl_version is not None:
            if not hasattr(ssl, f"PROTOCOL_{ssl_version}"):
                log.error("Unknown SSL protocol %s", ssl_version)
                sys.exit(1)
            ssl_args["ssl_version"] = getattr(ssl, f"PROTOCOL_{ssl_version}")

        return ssl_args

    def _fill_certificate_fields(self, subject: object) -> None:
        """Fill standard certificate subject fields."""
        subject.C = "WW"
        subject.O = "Butterfly"
        subject.OU = "Butterfly Terminal"
        subject.ST = "World Wide"
        subject.L = "Terminal"

    def _write_file(self, filepath: str, content: bytes) -> None:
        """Write binary content to file."""
        with open(filepath, "wb") as fd:
            fd.write(content)
        log.info("Writing %s", filepath)

    def _read_file(self, filepath: str) -> bytes:
        """Read binary content from file."""
        log.info("Reading %s", filepath)
        with open(filepath, "rb") as fd:
            return fd.read()

    def _get_pkcs12_password(self) -> str:
        """Get password for PKCS12 certificate package."""
        while True:
            password = getpass.getpass("\nPKCS12 Password (can be blank): ")
            password2 = getpass.getpass("Verify Password (can be blank): ")
            if password == password2:
                return password
            print("Passwords do not match.")


class SSLCertificateOperations:
    """High-level SSL certificate operations for server startup."""

    @staticmethod
    def handle_certificate_generation(config: Dict) -> None:
        """Handle certificate generation operations and exit."""
        host = config["host"]
        ssl_dir = config["ssl_dir"]
        generate_certs = config["generate_certs"]
        generate_current_user_pkcs = config["generate_current_user_pkcs"]
        generate_user_pkcs = config["generate_user_pkcs"]

        manager = SSLCertificateManager(ssl_dir, host)

        if generate_certs:
            print(f"Generating certificates for {host} (change it with --host)\n")
            ca_cert, ca_pk = manager.generate_ca_certificate()
            manager.generate_server_certificate(ca_cert, ca_pk)
            print("\nNow you can run --generate-user-pkcs=user to generate user certificate.")
            sys.exit(0)

        if generate_current_user_pkcs or generate_user_pkcs:
            SSLCertificateOperations._handle_user_certificate_generation(
                manager, generate_current_user_pkcs, generate_user_pkcs
            )

    @staticmethod
    def _handle_user_certificate_generation(
        manager: SSLCertificateManager, generate_current_user_pkcs: bool, generate_user_pkcs: str
    ) -> None:
        """Handle user certificate generation."""
        from aetherterm.agentserver import utils

        try:
            current_user = utils.User()
        except Exception:
            current_user = None

        paths = manager.get_certificate_paths()

        if not all(os.path.exists(f) for f in [paths["ca"], paths["ca_key"]]):
            print("Please generate certificates using --generate-certs before")
            sys.exit(1)

        if generate_current_user_pkcs:
            username = current_user.name
        else:
            username = generate_user_pkcs

        if username != current_user.name and current_user.uid != 0:
            print("Cannot create certificate for another user with current privileges.")
            sys.exit(1)

        from OpenSSL import crypto

        ca_cert = crypto.load_certificate(crypto.FILETYPE_PEM, manager._read_file(paths["ca"]))
        ca_pk = crypto.load_privatekey(crypto.FILETYPE_PEM, manager._read_file(paths["ca_key"]))

        manager.generate_user_certificate(username, ca_cert, ca_pk)
        sys.exit(0)

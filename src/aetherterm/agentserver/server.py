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

import getpass
import logging
import os
import shutil
import socket
import ssl
import stat
import sys
import uuid
import webbrowser

import uvicorn

from aetherterm.agentserver import socket_handlers
from aetherterm.agentserver.containers import ApplicationContainer
from aetherterm.agentserver.routes import router

# Default configuration values (single source of truth)
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
    "ai_mode": "streaming",
    "ai_provider": "mock",
    "ai_api_key": None,
    "ai_model": "claude-3-5-sonnet-20241022",
    "conf": "",
    "ssl_dir": "",
}

log = logging.getLogger("aetherterm")


def setup_config_paths(config_dict):
    """Setup configuration paths and update the config dictionary."""
    if os.getuid() == 0:
        ev = os.getenv("XDG_CONFIG_DIRS", "/etc")
    else:
        ev = os.getenv(
            "XDG_CONFIG_HOME",
            os.path.join(os.getenv("HOME", os.path.expanduser("~")), ".config"),
        )

    aetherterm_dir = os.path.join(ev, "aetherterm")
    conf_file = os.path.join(aetherterm_dir, "aetherterm.conf")
    ssl_dir = os.path.join(aetherterm_dir, "ssl")

    config_dict["conf"] = conf_file
    config_dict["ssl_dir"] = ssl_dir

    if not os.path.exists(conf_file):
        try:
            default_conf_path = os.path.join(
                os.path.abspath(os.path.dirname(__file__)), "aetherterm.conf.default"
            )
            shutil.copy(default_conf_path, conf_file)
            print("aetherterm.conf installed in %s" % conf_file)
        except Exception as e:
            print(f"Could not install default aetherterm.conf: {e}")

    return config_dict


def _configure_logging(config):
    """Configure logging based on debug/more settings."""
    log_level = logging.WARNING
    if config.get("debug"):
        log_level = logging.INFO
        if config.get("more"):
            log_level = logging.DEBUG

    for logger_name in ("uvicorn.access", "uvicorn.error", "aetherterm"):
        logging.getLogger(logger_name).setLevel(log_level)

    return log_level


def _register_socket_handlers(sio):
    """Register all Socket.IO event handlers on the given server instance."""
    socket_handlers.set_sio_instance(sio)

    # Terminal handlers
    sio.on("connect", socket_handlers.connect)
    sio.on("disconnect", socket_handlers.disconnect)
    sio.on("create_terminal", socket_handlers.create_terminal)
    sio.on("terminal_input", socket_handlers.terminal_input)
    sio.on("terminal_resize", socket_handlers.terminal_resize)

    # AI handlers
    sio.on("ai_chat_message", socket_handlers.ai_chat_message)
    sio.on("ai_terminal_analysis", socket_handlers.ai_terminal_analysis)
    sio.on("ai_get_info", socket_handlers.ai_get_info)

    # Wrapper session sync handlers
    sio.on("wrapper_session_sync", socket_handlers.wrapper_session_sync)
    sio.on("get_wrapper_sessions", socket_handlers.get_wrapper_sessions)

    # Block/Unblock handlers
    sio.on("unblock_request", socket_handlers.unblock_request)
    sio.on("get_block_status", socket_handlers.get_block_status)


def _build_config(**kwargs):
    """Build configuration from defaults, config paths, and overrides."""
    config = DEFAULT_CONFIG.copy()
    config = setup_config_paths(config)
    config.update(kwargs)
    return config


def _handle_cert_generation(config):
    """Handle SSL certificate generation commands. Returns True if program should exit."""
    host = config["host"]
    ssl_dir = config["ssl_dir"]
    generate_certs = config["generate_certs"]
    generate_current_user_pkcs = config["generate_current_user_pkcs"]
    generate_user_pkcs = config["generate_user_pkcs"]

    if not os.path.exists(ssl_dir):
        os.makedirs(ssl_dir)

    def to_abs(file):
        return os.path.join(ssl_dir, file)

    ca, ca_key, cert, cert_key, pkcs12 = map(
        to_abs,
        [
            "aetherterm_ca.crt",
            "aetherterm_ca.key",
            "aetherterm_%s.crt",
            "aetherterm_%s.key",
            "%s.p12",
        ],
    )

    def fill_fields(subject):
        subject.C = "WW"
        subject.O = "AetherTerm"
        subject.OU = "AetherTerm Terminal"
        subject.ST = "World Wide"
        subject.L = "Terminal"

    def write_file(file, content):
        with open(file, "wb") as fd:
            fd.write(content)
        print("Writing %s" % file)

    def read_file(file):
        print("Reading %s" % file)
        with open(file, "rb") as fd:
            return fd.read()

    def b(s):
        return s.encode("utf-8")

    if generate_certs:
        from OpenSSL import crypto

        print("Generating certificates for %s (change it with --host)\n" % host)

        if not os.path.exists(ca) and not os.path.exists(ca_key):
            print("Root certificate not found, generating it")
            ca_pk = crypto.PKey()
            ca_pk.generate_key(crypto.TYPE_RSA, 2048)
            ca_cert = crypto.X509()
            ca_cert.set_version(2)
            ca_cert.get_subject().CN = "AetherTerm CA on %s" % socket.gethostname()
            fill_fields(ca_cert.get_subject())
            ca_cert.set_serial_number(uuid.uuid4().int)
            ca_cert.gmtime_adj_notBefore(0)
            ca_cert.gmtime_adj_notAfter(315360000)
            ca_cert.set_issuer(ca_cert.get_subject())
            ca_cert.set_pubkey(ca_pk)
            ca_cert.add_extensions(
                [
                    crypto.X509Extension(b("basicConstraints"), True, b("CA:TRUE, pathlen:0")),
                    crypto.X509Extension(b("keyUsage"), True, b("keyCertSign, cRLSign")),
                    crypto.X509Extension(
                        b("subjectKeyIdentifier"), False, b("hash"), subject=ca_cert
                    ),
                ]
            )
            ca_cert.add_extensions(
                [
                    crypto.X509Extension(
                        b("authorityKeyIdentifier"),
                        False,
                        b("issuer:always, keyid:always"),
                        issuer=ca_cert,
                        subject=ca_cert,
                    )
                ]
            )
            ca_cert.sign(ca_pk, "sha512")

            write_file(ca, crypto.dump_certificate(crypto.FILETYPE_PEM, ca_cert))
            write_file(ca_key, crypto.dump_privatekey(crypto.FILETYPE_PEM, ca_pk))
            os.chmod(ca_key, stat.S_IRUSR | stat.S_IWUSR)
        else:
            print("Root certificate found, using it")
            ca_cert = crypto.load_certificate(crypto.FILETYPE_PEM, read_file(ca))
            ca_pk = crypto.load_privatekey(crypto.FILETYPE_PEM, read_file(ca_key))

        server_pk = crypto.PKey()
        server_pk.generate_key(crypto.TYPE_RSA, 2048)
        server_cert = crypto.X509()
        server_cert.set_version(2)
        server_cert.get_subject().CN = host
        server_cert.add_extensions(
            [
                crypto.X509Extension(b("basicConstraints"), False, b("CA:FALSE")),
                crypto.X509Extension(
                    b("subjectKeyIdentifier"), False, b("hash"), subject=server_cert
                ),
                crypto.X509Extension(b("subjectAltName"), False, b("DNS:%s" % host)),
            ]
        )
        server_cert.add_extensions(
            [
                crypto.X509Extension(
                    b("authorityKeyIdentifier"),
                    False,
                    b("issuer:always, keyid:always"),
                    issuer=ca_cert,
                    subject=ca_cert,
                )
            ]
        )
        fill_fields(server_cert.get_subject())
        server_cert.set_serial_number(uuid.uuid4().int)
        server_cert.gmtime_adj_notBefore(0)
        server_cert.gmtime_adj_notAfter(315360000)
        server_cert.set_issuer(ca_cert.get_subject())
        server_cert.set_pubkey(server_pk)
        server_cert.sign(ca_pk, "sha512")

        write_file(cert % host, crypto.dump_certificate(crypto.FILETYPE_PEM, server_cert))
        write_file(cert_key % host, crypto.dump_privatekey(crypto.FILETYPE_PEM, server_pk))
        os.chmod(cert_key % host, stat.S_IRUSR | stat.S_IWUSR)

        print("\nNow you can run --generate-user-pkcs=user to generate user certificate.")
        return True

    if generate_current_user_pkcs or generate_user_pkcs:
        from aetherterm.agentserver.utils import User

        try:
            current_user = User()
        except Exception:
            current_user = None

        from OpenSSL import crypto

        if not all(map(os.path.exists, [ca, ca_key])):
            print("Please generate certificates using --generate-certs before")
            sys.exit(1)

        if generate_current_user_pkcs:
            user = current_user.name
        else:
            user = generate_user_pkcs

        if user != current_user.name and current_user.uid != 0:
            print("Cannot create certificate for another user with current privileges.")
            sys.exit(1)

        ca_cert = crypto.load_certificate(crypto.FILETYPE_PEM, read_file(ca))
        ca_pk = crypto.load_privatekey(crypto.FILETYPE_PEM, read_file(ca_key))

        client_pk = crypto.PKey()
        client_pk.generate_key(crypto.TYPE_RSA, 2048)

        client_cert = crypto.X509()
        client_cert.set_version(2)
        client_cert.get_subject().CN = user
        fill_fields(client_cert.get_subject())
        client_cert.set_serial_number(uuid.uuid4().int)
        client_cert.gmtime_adj_notBefore(0)
        client_cert.gmtime_adj_notAfter(315360000)
        client_cert.set_issuer(ca_cert.get_subject())
        client_cert.set_pubkey(client_pk)
        client_cert.sign(client_pk, "sha512")
        client_cert.sign(ca_pk, "sha512")

        pfx = crypto.PKCS12()
        pfx.set_certificate(client_cert)
        pfx.set_privatekey(client_pk)
        pfx.set_ca_certificates([ca_cert])
        pfx.set_friendlyname(("%s cert for aetherterm" % user).encode("utf-8"))

        while True:
            password = getpass.getpass("\nPKCS12 Password (can be blank): ")
            password2 = getpass.getpass("Verify Password (can be blank): ")
            if password == password2:
                break
            print("Passwords do not match.")

        print("")
        write_file(pkcs12 % user, pfx.export(password.encode("utf-8")))
        os.chmod(pkcs12 % user, stat.S_IRUSR | stat.S_IWUSR)
        return True

    return False


def _build_ssl_args(config):
    """Build SSL arguments for uvicorn from config. Returns empty dict if unsecure."""
    host = config["host"]
    ssl_dir = config["ssl_dir"]
    unsecure = config["unsecure"]
    ssl_version = config["ssl_version"]

    if unsecure:
        return {}

    def to_abs(file):
        return os.path.join(ssl_dir, file)

    ca = to_abs("aetherterm_ca.crt")
    cert = to_abs("aetherterm_%s.crt") % host
    cert_key = to_abs("aetherterm_%s.key") % host

    if not all(map(os.path.exists, [cert, cert_key, ca])):
        log.error("Unable to find aetherterm certificate for host %s", host)
        log.error(cert)
        log.error(cert_key)
        log.error(ca)
        log.error("Can't run aetherterm without certificate.\n")
        log.error(
            "Either generate them using --generate-certs --host=host "
            "or run as --unsecure (NOT RECOMMENDED)\n"
        )
        sys.exit(1)

    ssl_args = {
        "ssl_certfile": cert,
        "ssl_keyfile": cert_key,
        "ssl_ca_certs": ca,
        "ssl_cert_reqs": ssl.CERT_REQUIRED,
    }

    if ssl_version is not None:
        if not hasattr(ssl, f"PROTOCOL_{ssl_version}"):
            log.error("Unknown SSL protocol %s", ssl_version)
            sys.exit(1)
        ssl_args["ssl_version"] = getattr(ssl, f"PROTOCOL_{ssl_version}")

    return ssl_args


async def start_server(**kwargs):
    """Start the AetherTerm server with dependency injection."""
    config = _build_config(**kwargs)
    log_level = _configure_logging(config)

    if config["i_hereby_declare_i_dont_want_any_security_whatsoever"]:
        config["unsecure"] = True

    # Handle certificate generation (exits if generation was requested)
    if _handle_cert_generation(config):
        sys.exit(0)

    ssl_args = _build_ssl_args(config)

    # Configure the dependency injection container
    container = ApplicationContainer()
    container.config.from_dict(config)
    container.wire(
        modules=[
            "aetherterm.agentserver.server",
            "aetherterm.agentserver.terminals",
            "aetherterm.agentserver.utils",
            "aetherterm.agentserver.socket_handlers.terminal_handlers",
            "aetherterm.agentserver.routes",
        ]
    )

    log.info("Starting server")

    app = container.app()
    sio = container.sio()

    _register_socket_handlers(sio)

    uri_root_path = config["uri_root_path"]
    app.other_asgi_app.include_router(router, prefix=uri_root_path)

    log_level_name = logging.getLevelName(log_level).lower()
    if log_level_name == "warning":
        log_level_name = "warn"

    server = uvicorn.Server(
        uvicorn.Config(
            app=app,
            host=config["host"],
            port=config["port"],
            log_level=log_level_name,
            reload=config.get("debug", False),
            **ssl_args,
        )
    )

    unsecure = config["unsecure"]
    host = config["host"]
    port = config["port"]
    url = f"http{'s' if not unsecure else ''}://{host}:{port}/{uri_root_path.strip('/') + '/' if uri_root_path else ''}"

    if not config["one_shot"] or not webbrowser.open(url):
        log.warning("AetherTerm is ready, open your browser to: %s", url)

    await server.serve()


# --- Factory functions for ASGI servers (uvicorn/hypercorn compatibility) ---


def create_factory_app(**kwargs):
    """Create the AetherTerm AgentServer ASGI application with dependency injection."""
    import socketio
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles

    config = DEFAULT_CONFIG.copy()
    config.update(kwargs)

    from aetherterm.agentserver.containers import configure_container

    container = configure_container(config)

    fastapi_app = FastAPI()
    static_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    if os.path.exists(static_path):
        fastapi_app.mount("/static", StaticFiles(directory=static_path), name="static")

    from aetherterm.agentserver.routes import router as factory_router

    fastapi_app.include_router(factory_router)

    sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")

    uri_root_path = config.get("uri_root_path", "")
    socketio_path = f"{uri_root_path}/socket.io" if uri_root_path else "/socket.io"

    asgi_app = socketio.ASGIApp(
        socketio_server=sio, other_asgi_app=fastapi_app, socketio_path=socketio_path
    )

    return asgi_app, sio, container, config


def setup_app(**kwargs):
    """Setup the application and prepare it for running."""
    from aetherterm.agentserver.utils import prepare_ssl_certs

    prepare_ssl_certs(**kwargs)

    asgi_app, sio, container, config = create_factory_app(**kwargs)

    _register_socket_handlers(sio)

    log.info("AetherTerm AgentServer application setup complete")

    return asgi_app


def create_asgi_app():
    """
    Factory function for creating the ASGI application.
    This is called by uvicorn/hypercorn when using:
    uvicorn aetherterm.agentserver.server:create_asgi_app --factory
    """
    config = {
        "host": os.getenv("AETHERTERM_HOST", "localhost"),
        "port": int(os.getenv("AETHERTERM_PORT", "57575")),
        "debug": os.getenv("AETHERTERM_DEBUG", "").lower() in ("true", "1", "yes"),
        "more": os.getenv("AETHERTERM_MORE", "").lower() in ("true", "1", "yes"),
        "unsecure": os.getenv("AETHERTERM_UNSECURE", "").lower() in ("true", "1", "yes"),
        "uri_root_path": os.getenv("AETHERTERM_URI_ROOT_PATH", ""),
        "login": os.getenv("AETHERTERM_LOGIN", "").lower() in ("true", "1", "yes"),
        "pam_profile": os.getenv("AETHERTERM_PAM_PROFILE", ""),
        "ai_mode": os.getenv("AETHERTERM_AI_MODE", "streaming"),
        "ai_provider": os.getenv(
            "AETHERTERM_AI_PROVIDER",
            "anthropic" if os.getenv("ANTHROPIC_API_KEY") else "mock",
        ),
        "ai_api_key": os.getenv("ANTHROPIC_API_KEY"),
        "ai_model": os.getenv("AETHERTERM_AI_MODEL", "claude-3-5-sonnet-20241022"),
    }

    return setup_app(**config)

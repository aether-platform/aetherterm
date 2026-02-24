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
from aetherterm.agentserver.utils.ssl_certs import prepare_ssl_certs

# Default configuration values
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
    "ai_mode": "streaming",  # New option for AI assistance mode
    "ai_provider": "mock",  # AI provider (anthropic, mock)
    "ai_api_key": None,  # AI API key (will be read from env)
    "ai_model": "claude-3-5-sonnet-20241022",  # AI model
    "conf": "",  # Will be set dynamically
    "ssl_dir": "",  # Will be set dynamically
}


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
                os.path.abspath(os.path.dirname(__file__)), "butterfly.conf.default"
            )
            shutil.copy(default_conf_path, conf_file)
            print("aetherterm.conf installed in %s" % conf_file)
        except Exception as e:
            print(f"Could not install default aetherterm.conf: {e}")

    return config_dict


# Configure logging
# This part will be handled by the container's logging_level provider
# for logger_name in ('hypercorn.access', 'hypercorn.error', 'aetherterm'):
#     level = logging.WARNING
#     if options["debug"]:
#         level = logging.INFO
#         if options["more"]:
#             level = logging.DEBUG
#     logging.getLogger(logger_name).setLevel(level)


log = logging.getLogger("aetherterm")


def create_app(**kwargs):
    """Create the Butterfly ASGI application with dependency injection."""
    # Start with default config
    config = DEFAULT_CONFIG.copy()

    # Setup config paths first (may be overridden by kwargs)
    config = setup_config_paths(config)

    # Override with Click-provided values (this ensures CLI args take precedence)
    config.update(kwargs)

    # Configure the dependency injection container
    container = ApplicationContainer()
    container.config.from_dict(config)
    container.wire(
        modules=[
            "aetherterm.agentserver.server",
            "aetherterm.agentserver.terminals",
            "aetherterm.agentserver.utils",
            "aetherterm.agentserver.socket_handlers",
            "aetherterm.agentserver.routes",  # Wire routes module
        ]
    )

    return container, config


async def start_server(**kwargs):
    """Start the Butterfly server with dependency injection."""
    _asgi_app, _sio, container, config, _fastapi_app = create_app(**kwargs)

    host = config["host"]
    port = config["port"]
    unsecure = config["unsecure"]
    ssl_dir = config["ssl_dir"]
    generate_certs = config["generate_certs"]
    generate_current_user_pkcs = config["generate_current_user_pkcs"]
    generate_user_pkcs = config["generate_user_pkcs"]
    ssl_version = config["ssl_version"]
    i_hereby_declare_i_dont_want_any_security_whatsoever = config[
        "i_hereby_declare_i_dont_want_any_security_whatsoever"
    ]
    one_shot = config["one_shot"]
    uri_root_path = config["uri_root_path"]

    # Reconfigure logging based on container config
    log_level = logging.WARNING
    if config["debug"]:
        log_level = logging.INFO
        if config["more"]:
            log_level = logging.DEBUG

    for logger_name in ("uvicorn.access", "uvicorn.error", "aetherterm"):
        logging.getLogger(logger_name).setLevel(log_level)

    if i_hereby_declare_i_dont_want_any_security_whatsoever:
        unsecure = True

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
        subject.O = "Butterfly"
        subject.OU = "Butterfly Terminal"
        subject.ST = "World Wide"
        subject.L = "Terminal"

    def write(file, content):
        with open(file, "wb") as fd:
            fd.write(content)
        print("Writing %s" % file)

    def read(file):
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
            ca_cert.get_subject().CN = "Butterfly CA on %s" % socket.gethostname()
            fill_fields(ca_cert.get_subject())
            ca_cert.set_serial_number(uuid.uuid4().int)
            ca_cert.gmtime_adj_notBefore(0)  # From now
            ca_cert.gmtime_adj_notAfter(315360000)  # to 10y
            ca_cert.set_issuer(ca_cert.get_subject())  # Self signed
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

            write(ca, crypto.dump_certificate(crypto.FILETYPE_PEM, ca_cert))
            write(ca_key, crypto.dump_privatekey(crypto.FILETYPE_PEM, ca_pk))
            os.chmod(ca_key, stat.S_IRUSR | stat.S_IWUSR)  # 0o600 perms
        else:
            print("Root certificate found, using it")
            ca_cert = crypto.load_certificate(crypto.FILETYPE_PEM, read(ca))
            ca_pk = crypto.load_privatekey(crypto.FILETYPE_PEM, read(ca_key))

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
        server_cert.gmtime_adj_notBefore(0)  # From now
        server_cert.gmtime_adj_notAfter(315360000)  # to 10y
        server_cert.set_issuer(ca_cert.get_subject())  # Signed by ca
        server_cert.set_pubkey(server_pk)
        server_cert.sign(ca_pk, "sha512")

        write(cert % host, crypto.dump_certificate(crypto.FILETYPE_PEM, server_cert))
        write(cert_key % host, crypto.dump_privatekey(crypto.FILETYPE_PEM, server_pk))
        os.chmod(cert_key % host, stat.S_IRUSR | stat.S_IWUSR)  # 0o600 perms

        print("\nNow you can run --generate-user-pkcs=user to generate user certificate.")
        sys.exit(0)

    if generate_current_user_pkcs or generate_user_pkcs:
        from aetherterm.agentserver import utils

        try:
            current_user = utils.User()
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

        ca_cert = crypto.load_certificate(crypto.FILETYPE_PEM, read(ca))
        ca_pk = crypto.load_privatekey(crypto.FILETYPE_PEM, read(ca_key))

        client_pk = crypto.PKey()
        client_pk.generate_key(crypto.TYPE_RSA, 2048)

        client_cert = crypto.X509()
        client_cert.set_version(2)
        client_cert.get_subject().CN = user
        fill_fields(client_cert.get_subject())
        client_cert.set_serial_number(uuid.uuid4().int)
        client_cert.gmtime_adj_notBefore(0)  # From now
        client_cert.gmtime_adj_notAfter(315360000)  # to 10y
        client_cert.set_issuer(ca_cert.get_subject())  # Signed by ca
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
        write(pkcs12 % user, pfx.export(password.encode("utf-8")))
        os.chmod(pkcs12 % user, stat.S_IRUSR | stat.S_IWUSR)  # 0o600 perms
        sys.exit(0)

    # Set up SSL options if not unsecure
    ssl_args = {}
    if not unsecure:
        if not all(map(os.path.exists, [cert % host, cert_key % host, ca])):
            log.error("Unable to find aetherterm certificate for host %s", host)
            log.error(cert % host)
            log.error(cert_key % host)
            log.error(ca)
            log.error("Can't run aetherterm without certificate.\n")
            log.error(
                "Either generate them using --generate-certs --host=host "
                "or run as --unsecure (NOT RECOMMENDED)\n"
            )
            log.error(
                "For more information go to http://paradoxxxzero.github.io/"
                "2014/03/21/aetherterm-with-ssl-auth.html\n"
            )
            sys.exit(1)

        ssl_args["ssl_certfile"] = cert % host
        ssl_args["ssl_keyfile"] = cert_key % host
        ssl_args["ssl_ca_certs"] = ca
        ssl_args["ssl_cert_reqs"] = ssl.CERT_REQUIRED

        if ssl_version is not None:
            if not hasattr(ssl, f"PROTOCOL_{ssl_version}"):
                log.error("Unknown SSL protocol %s", ssl_version)
                sys.exit(1)
            ssl_args["ssl_version"] = getattr(ssl, f"PROTOCOL_{ssl_version}")

    log.info("Starting server")

    # Get the ASGI application from the container
    app = container.app()
    sio = container.sio()

    # Set the socket.io instance in handlers module
    socket_handlers.set_sio_instance(sio)

    # Initialize AgentPaneManager and MessageRouter
    from aetherterm.agentserver.agent_pane_manager import AgentPaneManager, MessageRouter

    pane_manager = AgentPaneManager(broadcast_fn=socket_handlers.broadcast_to_session)
    message_router = MessageRouter(pane_manager)
    pane_manager.set_message_router(message_router)
    socket_handlers.set_pane_manager(pane_manager)

    # Register Socket.IO event handlers
    sio.on("connect", socket_handlers.connect)
    sio.on("disconnect", socket_handlers.disconnect)
    sio.on("create_terminal", socket_handlers.create_terminal)
    sio.on("terminal_input", socket_handlers.terminal_input)
    sio.on("terminal_resize", socket_handlers.terminal_resize)

    # Register AI-related event handlers
    sio.on("ai_chat_message", socket_handlers.ai_chat_message)
    sio.on("ai_terminal_analysis", socket_handlers.ai_terminal_analysis)
    sio.on("ai_get_info", socket_handlers.ai_get_info)

    # Register Wrapper session sync handlers
    sio.on("wrapper_session_sync", socket_handlers.wrapper_session_sync)
    sio.on("get_wrapper_sessions", socket_handlers.get_wrapper_sessions)

    # Register Block/Unblock handlers
    sio.on("unblock_request", socket_handlers.unblock_request)
    sio.on("get_block_status", socket_handlers.get_block_status)

    # Register Pane management handlers
    sio.on("pane_create", socket_handlers.pane_create)
    sio.on("pane_destroy", socket_handlers.pane_destroy)
    sio.on("pane_resize", socket_handlers.pane_resize)
    sio.on("pane_focus", socket_handlers.pane_focus)
    sio.on("pane_list", socket_handlers.pane_list)
    sio.on("pane_input", socket_handlers.pane_input)
    sio.on("session_list", socket_handlers.session_list)

    # Register AI command execution handlers
    sio.on("ai_execute_command", socket_handlers.ai_execute_command)
    sio.on("ai_set_execution_mode", socket_handlers.ai_set_execution_mode)

    # Mount the FastAPI router onto the main ASGI app
    app.other_asgi_app.include_router(router, prefix=uri_root_path)

    # Start the Uvicorn server
    log_level_name = logging.getLevelName(log_level).lower()
    if log_level_name == "warning":
        log_level_name = "warn"  # uvicorn uses 'warn' instead of 'warning'

    server = uvicorn.Server(
        uvicorn.Config(
            app=app,
            host=host,
            port=port,
            log_level=log_level_name,
            reload=config.get("debug", False),  # Enable reload in debug mode
            **ssl_args,
        )
    )

    # Show URL before starting
    url = f"http{'s' if not unsecure else ''}://{host}:{port}/{uri_root_path.strip('/') + '/' if uri_root_path else ''}"

    if not one_shot or not webbrowser.open(url):
        log.warning("Butterfly is ready, open your browser to: %s", url)

    await server.serve()


# Factory functions for ASGI servers (uvicorn/hypercorn compatibility)


def create_app(**kwargs):
    """Create the AetherTerm AgentServer ASGI application with dependency injection."""
    import socketio
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles

    # Default configuration values
    default_config = {
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
    }

    # Start with default config and override with provided kwargs
    config = default_config.copy()
    config.update(kwargs)

    # Configure the dependency injection container
    from aetherterm.agentserver.containers import configure_container

    container = configure_container(config)

    # Create FastAPI application
    fastapi_app = FastAPI()
    static_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    if os.path.exists(static_path):
        fastapi_app.mount("/static", StaticFiles(directory=static_path), name="static")

    # Include router
    from aetherterm.agentserver.routes import router

    fastapi_app.include_router(router)

    # Create Socket.IO server
    sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")

    # Create combined ASGI application
    uri_root_path = config.get("uri_root_path", "")
    socketio_path = f"{uri_root_path}/socket.io" if uri_root_path else "/socket.io"

    asgi_app = socketio.ASGIApp(
        socketio_server=sio, other_asgi_app=fastapi_app, socketio_path=socketio_path
    )

    return asgi_app, sio, container, config, fastapi_app


def setup_app(**kwargs):
    """Setup the application and prepare it for running."""
    # Handle certificate generation first
    prepare_ssl_certs(**kwargs)

    # Create and return the ASGI app
    asgi_app, sio, container, config, fastapi_app = create_app(**kwargs)

    # Set the socket.io instance in handlers module
    from aetherterm.agentserver import socket_handlers

    socket_handlers.set_sio_instance(sio)

    # Initialize AgentPaneManager and MessageRouter
    from aetherterm.agentserver.agent_pane_manager import AgentPaneManager, MessageRouter

    pane_manager = AgentPaneManager(broadcast_fn=socket_handlers.broadcast_to_session)
    message_router = MessageRouter(pane_manager)
    pane_manager.set_message_router(message_router)
    socket_handlers.set_pane_manager(pane_manager)

    # Register Socket.IO event handlers
    sio.on("connect", socket_handlers.connect)
    sio.on("disconnect", socket_handlers.disconnect)
    sio.on("create_terminal", socket_handlers.create_terminal)
    sio.on("terminal_input", socket_handlers.terminal_input)
    sio.on("terminal_resize", socket_handlers.terminal_resize)

    # Register AI-specific handlers
    sio.on("ai_chat_message", socket_handlers.ai_chat_message)
    sio.on("ai_terminal_analysis", socket_handlers.ai_terminal_analysis)
    sio.on("ai_get_info", socket_handlers.ai_get_info)

    # Register Wrapper session sync handlers
    sio.on("wrapper_session_sync", socket_handlers.wrapper_session_sync)
    sio.on("get_wrapper_sessions", socket_handlers.get_wrapper_sessions)
    sio.on("unblock_request", socket_handlers.unblock_request)
    sio.on("get_block_status", socket_handlers.get_block_status)

    # Register Pane management handlers
    sio.on("pane_create", socket_handlers.pane_create)
    sio.on("pane_destroy", socket_handlers.pane_destroy)
    sio.on("pane_resize", socket_handlers.pane_resize)
    sio.on("pane_focus", socket_handlers.pane_focus)
    sio.on("pane_list", socket_handlers.pane_list)
    sio.on("pane_input", socket_handlers.pane_input)
    sio.on("session_list", socket_handlers.session_list)

    # Register AI command execution handlers
    sio.on("ai_execute_command", socket_handlers.ai_execute_command)
    sio.on("ai_set_execution_mode", socket_handlers.ai_set_execution_mode)

    # Set up auto-blocker integration
    from aetherterm.agentserver.auto_blocker import set_socket_io_instance

    set_socket_io_instance(sio)

    # ZMQ Broker integration (feature flag: AETHERTERM_ZMQ_ENABLED)
    zmq_enabled = os.getenv("AETHERTERM_ZMQ_ENABLED", "").lower() in ("true", "1", "yes")
    if zmq_enabled:
        from aetherterm.common.zmq.zmq_bridge import SocketIOZMQBridge
        from aetherterm.common.zmq.zmq_broker import ZMQBroker
        from aetherterm.common.zmq.zmq_config import ZMQConfig

        zmq_config = ZMQConfig(
            enabled=True,
            broker_router_endpoint=os.getenv("AETHERTERM_ZMQ_ROUTER", "tcp://127.0.0.1:5560"),
            broker_pub_endpoint=os.getenv("AETHERTERM_ZMQ_PUB", "tcp://127.0.0.1:5561"),
            broker_push_endpoint=os.getenv("AETHERTERM_ZMQ_PUSH", "tcp://127.0.0.1:5562"),
        )

        zmq_broker = ZMQBroker(zmq_config)
        zmq_bridge = SocketIOZMQBridge(sio, zmq_broker)

        # Store references for access by handlers
        socket_handlers.set_zmq_broker(zmq_broker)
        socket_handlers.set_zmq_bridge(zmq_bridge)

        # Wire up command handlers (AgentShell Observer Pattern)
        zmq_bridge.set_command_inject_handler(socket_handlers.handle_zmq_command_inject)
        zmq_bridge.set_command_propose_handler(socket_handlers.handle_zmq_command_propose)

        # Start broker and bridge via FastAPI startup event
        @fastapi_app.on_event("startup")
        async def start_zmq():
            await zmq_broker.start()
            await zmq_bridge.start()
            log.info("ZMQ Broker and Bridge started")

        log.info("ZMQ integration enabled")
    else:
        log.info("ZMQ integration disabled (set AETHERTERM_ZMQ_ENABLED=true to enable)")

    log.info("AetherTerm AgentServer application setup complete")

    return asgi_app


def create_asgi_app():
    """Factory function for creating the ASGI application.
    This is called by uvicorn/hypercorn when using:
    uvicorn aetherterm.agentserver.server:create_asgi_app --factory
    """
    import os

    # Get configuration from environment variables
    config = {}

    # Basic settings
    config["host"] = os.getenv("AETHERTERM_HOST", "localhost")
    config["port"] = int(os.getenv("AETHERTERM_PORT", "57575"))
    config["debug"] = os.getenv("AETHERTERM_DEBUG", "").lower() in ("true", "1", "yes")
    config["more"] = os.getenv("AETHERTERM_MORE", "").lower() in ("true", "1", "yes")
    config["unsecure"] = os.getenv("AETHERTERM_UNSECURE", "").lower() in ("true", "1", "yes")
    config["uri_root_path"] = os.getenv("AETHERTERM_URI_ROOT_PATH", "")
    config["login"] = os.getenv("AETHERTERM_LOGIN", "").lower() in ("true", "1", "yes")
    config["pam_profile"] = os.getenv("AETHERTERM_PAM_PROFILE", "")
    config["ai_mode"] = os.getenv("AETHERTERM_AI_MODE", "streaming")
    config["ai_provider"] = os.getenv(
        "AETHERTERM_AI_PROVIDER", "anthropic" if os.getenv("ANTHROPIC_API_KEY") else "mock"
    )
    config["ai_api_key"] = os.getenv("ANTHROPIC_API_KEY")
    config["ai_model"] = os.getenv("AETHERTERM_AI_MODEL", "claude-3-5-sonnet-20241022")

    # Setup and return the app
    return setup_app(**config)


# Module-level app instance for simple usage
app = None


if __name__ == "__main__":
    # This block is now handled by scripts/aetherterm
    pass

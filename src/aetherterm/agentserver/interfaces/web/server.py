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

import logging
import os
import ssl
import stat
import sys
import uuid
import socket
import getpass
import webbrowser
import uvicorn

# OpenTelemetry imports
from aetherterm.agentserver.infrastructure.observability.telemetry import (
    initialize_telemetry,
    get_telemetry
)

from aetherterm.agentserver.interfaces.web.config import (
    DEFAULT_CONFIG,
    setup_config_paths,
    parse_environment_config,
)
from aetherterm.agentserver.interfaces.web.config.ssl_manager import (
    SSLCertificateManager,
    SSLCertificateOperations
)
from aetherterm.agentserver.interfaces.web.config.app_factory import (
    ApplicationFactoryRegistry,
    LegacyApplicationFactory
)
from aetherterm.agentserver.interfaces.web.config.lifecycle_manager import (
    ServerSetupOrchestrator,
    UvicornServerManager
)
from aetherterm.agentserver.endpoint.routes.routes import router
from aetherterm.agentserver.endpoint.websocket import socket_handlers


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
    factory = LegacyApplicationFactory()
    return factory.create_app(**kwargs)


async def start_server(**kwargs):
    """Start the Butterfly server with dependency injection."""
    container, config = create_app(**kwargs)

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

    # Register Socket.IO event handlers
    sio.on("connect", socket_handlers.connect)
    sio.on("disconnect", socket_handlers.disconnect)
    sio.on("create_terminal", socket_handlers.create_terminal)
    sio.on("resume_workspace", socket_handlers.resume_workspace)
    sio.on("resume_terminal", socket_handlers.resume_terminal)
    sio.on("terminal_input", socket_handlers.terminal_input)
    sio.on("terminal_resize", socket_handlers.terminal_resize)
    sio.on("reconnect_session", socket_handlers.reconnect_session)
    sio.on("get_session_info", socket_handlers.get_session_info)
    
    # Workspace management handlers
    sio.on("save_workspace", socket_handlers.save_workspace)
    sio.on("load_workspace", socket_handlers.load_workspace)
    sio.on("list_workspaces", socket_handlers.list_workspaces)

    # Register Wrapper session sync handlers
    sio.on("wrapper_session_sync", socket_handlers.wrapper_session_sync)
    sio.on("get_wrapper_sessions", socket_handlers.get_wrapper_sessions)


    # P0 緊急対応: MainAgent-SubAgent通信ハンドラーを登録
    # DEPRECATED: 後方互換性のため一時的に保持（将来削除予定）
    # sio.on("response_request", socket_handlers.response_request)
    # sio.on("response_reply", socket_handlers.response_reply)

    # 現在使用中のハンドラー
    sio.on("agent_start_request", socket_handlers.agent_start_request)
    sio.on("control_message", socket_handlers.control_message)

    # 仕様インプットシステム
    sio.on("spec_upload", socket_handlers.spec_upload)
    sio.on("spec_query", socket_handlers.spec_query)

    # エージェント登録・初期化
    sio.on("agent_hello", socket_handlers.agent_hello)

    # ログ監視・解析
    sio.on("log_monitor_subscribe", socket_handlers.log_monitor_subscribe)
    sio.on("log_monitor_unsubscribe", socket_handlers.log_monitor_unsubscribe)
    sio.on("log_monitor_search", socket_handlers.log_monitor_search)

    
    # AI チャットとログ検索
    from aetherterm.agentserver.endpoint.handlers import ai_handlers
    sio.on("ai_chat_message", ai_handlers.ai_chat_message)  # Fixed: Match frontend event name
    sio.on("ai_log_search", ai_handlers.ai_log_search)
    sio.on("ai_search_suggestions", ai_handlers.ai_search_suggestions)
    sio.on("ai_get_info", ai_handlers.ai_get_info)  # Added: Missing handler for AI info

    # Supervisord プロセス管理 - check if module exists
    try:
        from aetherterm.agentserver.endpoint.handlers import supervisord_handlers
        sio.on("get_processes_list", supervisord_handlers.get_processes_list)
        sio.on("start_process", supervisord_handlers.start_process)
        sio.on("stop_process", supervisord_handlers.stop_process)
        sio.on("restart_process", supervisord_handlers.restart_process)
        sio.on("get_process_logs", supervisord_handlers.get_process_logs)
        sio.on("get_supervisord_status", supervisord_handlers.get_supervisord_status)
    except ImportError:
        log.warning("Supervisord handlers not available")

    # ログ監視バックグラウンドタスクを開始
    socket_handlers.start_log_monitoring_background_task()

    # 短期記憶機能とControlServer接続を初期化
    from aetherterm.agentserver.control_server_client import ControlServerClient
    from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal
    from aetherterm.agentserver.infrastructure.external.supervisord_mcp_service import initialize_supervisord_mcp

    # エージェントIDを生成（ホスト:ポートベース）
    agent_id = f"agentserver_{host}_{port}"

    # 短期記憶機能を初期化
    await AsyncioTerminal.initialize_short_term_memory(agent_id)

    # ControlServer接続を開始
    control_client = ControlServerClient(agent_id=agent_id)
    await control_client.start()

    # Supervisord MCP サービスを初期化
    try:
        await initialize_supervisord_mcp()
        log.info("Supervisord MCP service initialized successfully")
    except Exception as e:
        log.warning(f"Failed to initialize Supervisord MCP service: {e}")

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
    import os
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles
    from fastapi.middleware.cors import CORSMiddleware
    
    from aetherterm.agentserver.infrastructure.config.di_container import setup_di_container
    
    # Initialize DI container
    di_container = setup_di_container()

    # Start with default config and override with provided kwargs
    config = DEFAULT_CONFIG.copy()
    config.update(kwargs)

    # Initialize OpenTelemetry if enabled
    enable_telemetry = config.get("enable_telemetry", True)
    telemetry = None
    
    if enable_telemetry:
        try:
            telemetry = initialize_telemetry(
                service_name="aetherterm-agentserver",
                service_version="0.0.1", 
                environment=config.get("environment", "development"),
                enable_console_exporter=config.get("debug", False)
            )
            telemetry.setup_all()
        except Exception as e:
            log.warning(f"Failed to initialize telemetry: {e}")
    
    # Create FastAPI application
    fastapi_app = FastAPI(
        title="AetherTerm AgentServer API",
        description="Web-based terminal with AI agent integration",
        version="0.0.1"
    )
    
    # Apply OpenTelemetry instrumentation to FastAPI
    if telemetry:
        telemetry.instrument_app(fastapi_app)
    
    # Configure CORS
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"],  # Vite dev servers
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Calculate path to static files (go up from web/server.py to agentserver/static)
    static_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "static")
    if os.path.exists(static_path):
        fastapi_app.mount("/static", StaticFiles(directory=static_path), name="static")
        fastapi_app.mount("/assets", StaticFiles(directory=os.path.join(static_path, "assets")), name="assets")

    # Include routers
    fastapi_app.include_router(router)

    # Create Socket.IO server
    sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")

    # Create combined ASGI application
    uri_root_path = config.get("uri_root_path", "")
    socketio_path = f"{uri_root_path}/socket.io" if uri_root_path else "/socket.io"

    asgi_app = socketio.ASGIApp(
        socketio_server=sio, other_asgi_app=fastapi_app, socketio_path=socketio_path
    )

    return asgi_app, sio, di_container, config


def setup_app(**kwargs):
    """Setup the application and prepare it for running."""
    # Create and return the ASGI app
    asgi_app, sio, container, config = create_app(**kwargs)

    # Set the socket.io instance in handlers module
    from aetherterm.agentserver.endpoint.websocket import socket_handlers
    from aetherterm.core.container import DIContainer

    # Wire the DI container first
    DIContainer.wire_modules([socket_handlers])

    socket_handlers.set_sio_instance(sio)

    # Register Socket.IO event handlers
    sio.on("connect", socket_handlers.connect)
    sio.on("disconnect", socket_handlers.disconnect)
    sio.on("create_terminal", socket_handlers.create_terminal)
    sio.on("resume_workspace", socket_handlers.resume_workspace)
    sio.on("resume_terminal", socket_handlers.resume_terminal)
    sio.on("terminal_input", socket_handlers.terminal_input)
    sio.on("terminal_resize", socket_handlers.terminal_resize)
    sio.on("reconnect_session", socket_handlers.reconnect_session)

    # Register AI-specific handlers
    sio.on("wrapper_session_sync", socket_handlers.wrapper_session_sync)
    sio.on("get_wrapper_sessions", socket_handlers.get_wrapper_sessions)
    # TODO: Add unblock handlers when implemented
    # sio.on("unblock_request", socket_handlers.unblock_request)
    # sio.on("get_block_status", socket_handlers.get_block_status)

    # Register log monitoring handlers
    sio.on("log_monitor_subscribe", socket_handlers.log_monitor_subscribe)
    sio.on("log_monitor_unsubscribe", socket_handlers.log_monitor_unsubscribe)
    sio.on("log_monitor_search", socket_handlers.log_monitor_search)

    

    # P0 緊急対応: MainAgent-SubAgent通信ハンドラー
    # DEPRECATED: 後方互換性のため一時的に保持（将来削除予定）
    # sio.on("response_request", socket_handlers.response_request)
    # sio.on("response_reply", socket_handlers.response_reply)

    # 現在使用中のハンドラー
    sio.on("agent_start_request", socket_handlers.agent_start_request)
    sio.on("control_message", socket_handlers.control_message)

    # 仕様ドキュメント管理ハンドラー
    sio.on("spec_upload", socket_handlers.spec_upload)
    sio.on("spec_query", socket_handlers.spec_query)

    # エージェント初期化ハンドラー
    sio.on("agent_hello", socket_handlers.agent_hello)

    # AI Chat and Log Search handlers
    from aetherterm.agentserver.endpoint.handlers import ai_handlers
    sio.on("ai_chat_message", ai_handlers.ai_chat_message)
    sio.on("ai_log_search", ai_handlers.ai_log_search)
    sio.on("ai_search_suggestions", ai_handlers.ai_search_suggestions)
    sio.on("ai_get_info", ai_handlers.ai_get_info)

    # Set up auto-blocker integration
    try:
        from aetherterm.agentserver.auto_blocker import set_socket_io_instance
        set_socket_io_instance(sio)
    except ImportError as e:
        log.warning(f"Auto-blocker not available: {e}")

    # Initialize inventory service
    async def startup_inventory_service():
        try:
            from aetherterm.agentserver.services.inventory_service import inventory_service

            await inventory_service.initialize()
            log.info("Inventory service initialized successfully")
        except Exception as e:
            log.warning(f"Failed to initialize inventory service: {e}")

    # Initialize log processing
    async def startup_log_processing():
        try:
            from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal

            await AsyncioTerminal.start_log_processing()
            log.info("Log processing service started successfully")
        except Exception as e:
            log.warning(f"Failed to start log processing service: {e}")

    # Initialize context inference
    async def startup_context_inference():
        try:
            from aetherterm.agentserver.context_inference import initialize_context_inference
            from aetherterm.logprocessing.log_processing_manager import get_log_processing_manager

            # Get storage instances from log processing manager
            manager = get_log_processing_manager()
            if manager and manager.vector_storage and manager.sql_storage:
                initialize_context_inference(manager.vector_storage, manager.sql_storage)
                log.info("Context inference system initialized successfully")
            else:
                log.warning("Cannot initialize context inference: storage not available")
        except Exception as e:
            log.warning(f"Failed to initialize context inference: {e}")

    # Add startup and shutdown event handlers using lifespan
    async def startup():
        await startup_inventory_service()
        await startup_log_processing()
        await startup_context_inference()

        # Start log monitoring background task
        socket_handlers.start_log_monitoring_background_task()

    async def shutdown():
        try:
            from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal

            await AsyncioTerminal.stop_log_processing()
            log.info("Log processing service stopped")
        except Exception as e:
            log.warning(f"Error stopping log processing service: {e}")

    # Add event handlers to the FastAPI app (accessible through ASGI wrapper)
    if hasattr(asgi_app, "other_asgi_app") and asgi_app.other_asgi_app:
        fastapi_app = asgi_app.other_asgi_app
        fastapi_app.add_event_handler("startup", startup)
        fastapi_app.add_event_handler("shutdown", shutdown)

    log.info("AetherTerm AgentServer application setup complete")

    return asgi_app


def create_asgi_app():
    """
    Factory function for creating the ASGI application.
    This is called by uvicorn/hypercorn when using:
    uvicorn aetherterm.agentserver.server:create_asgi_app --factory
    """
    # Get configuration from environment variables using the config module
    config = parse_environment_config()

    # Setup and return the app
    return setup_app(**config)


# Module-level app instance for simple usage
app = None


if __name__ == "__main__":
    # This block is now handled by scripts/aetherterm
    pass

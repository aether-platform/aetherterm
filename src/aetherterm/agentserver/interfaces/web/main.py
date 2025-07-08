#!/usr/bin/env python

import logging
import os
import subprocess
import sys

import click

# SSL certificate preparation is now handled in server.py

# Configure logging for the launcher script
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("aetherterm.agentserver.launcher")


def set_environment_variables(kwargs):
    """Set environment variables for the ASGI app factory."""
    env = os.environ.copy()
    env["AETHERTERM_HOST"] = kwargs.get("host", "localhost")
    env["AETHERTERM_PORT"] = str(kwargs.get("port", 57575))
    env["AETHERTERM_DEBUG"] = "true" if kwargs.get("debug", False) else "false"
    env["AETHERTERM_MORE"] = "true" if kwargs.get("more", False) else "false"
    env["AETHERTERM_UNSECURE"] = "true" if kwargs.get("unsecure", False) else "false"
    env["AETHERTERM_URI_ROOT_PATH"] = kwargs.get("uri_root_path", "")
    env["AETHERTERM_LOGIN"] = "true" if kwargs.get("login", False) else "false"
    env["AETHERTERM_PAM_PROFILE"] = kwargs.get("pam_profile", "")
    env["AETHERTERM_AI_MODE"] = kwargs.get("ai_mode", "streaming")
    return env


def get_ssl_args(kwargs):
    """Get SSL arguments for the server."""
    ssl_args = []
    if not kwargs.get("unsecure", False):
        ssl_dir = kwargs.get(
            "ssl_dir", os.path.join(os.path.expanduser("~"), ".config", "aetherterm", "ssl")
        )
        host = kwargs.get("host", "localhost")
        cert = os.path.join(ssl_dir, f"aetherterm_{host}.crt")
        cert_key = os.path.join(ssl_dir, f"aetherterm_{host}.key")
        ca = os.path.join(ssl_dir, "aetherterm_ca.crt")

        if os.path.exists(cert) and os.path.exists(cert_key):
            return {"cert": cert, "cert_key": cert_key, "ca": ca}
    return None


def launch_uvicorn(kwargs):
    """Launch the application using uvicorn."""
    env = set_environment_variables(kwargs)

    # Build uvicorn command
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "aetherterm.agentserver.interfaces.web.server:create_asgi_app",
        "--factory",
        "--host",
        env["AETHERTERM_HOST"],
        "--port",
        env["AETHERTERM_PORT"],
    ]

    # Add SSL options
    ssl_config = get_ssl_args(kwargs)
    if ssl_config:
        cmd.extend(
            [
                "--ssl-keyfile",
                ssl_config["cert_key"],
                "--ssl-certfile",
                ssl_config["cert"],
                "--ssl-ca-certs",
                ssl_config["ca"],
                "--ssl-cert-reqs",
                "2",  # ssl.CERT_REQUIRED
            ]
        )

    # Configure logging level
    if kwargs.get("debug", False):
        if kwargs.get("more", False):
            cmd.extend(["--log-level", "debug"])
        else:
            cmd.extend(["--log-level", "info"])
        # Only add reload if reload is not explicitly disabled
        if not os.getenv("AETHERTERM_DISABLE_RELOAD"):
            cmd.append("--reload")
    else:
        cmd.extend(["--log-level", "warning"])

    log.info(f"Starting uvicorn: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, env=env)
    except KeyboardInterrupt:
        log.info("Server stopped by user")
    except Exception as e:
        log.error(f"Error running uvicorn: {e}")
        sys.exit(1)


def launch_hypercorn(kwargs):
    """Launch the application using hypercorn."""
    env = set_environment_variables(kwargs)

    # Build hypercorn command
    cmd = [
        sys.executable,
        "-m",
        "hypercorn",
        "aetherterm.agentserver.interfaces.web.server:create_asgi_app",
        "--factory",
        "--bind",
        f"{env['AETHERTERM_HOST']}:{env['AETHERTERM_PORT']}",
    ]

    # Add SSL options
    ssl_config = get_ssl_args(kwargs)
    if ssl_config:
        cmd.extend(
            [
                "--keyfile",
                ssl_config["cert_key"],
                "--certfile",
                ssl_config["cert"],
                "--ca-certs",
                ssl_config["ca"],
                "--verify-mode",
                "CERT_REQUIRED",
            ]
        )

    # Configure logging level
    if kwargs.get("debug", False):
        if kwargs.get("more", False):
            cmd.extend(["--log-level", "debug"])
        else:
            cmd.extend(["--log-level", "info"])
        # Only add reload if reload is not explicitly disabled
        if not os.getenv("AETHERTERM_DISABLE_RELOAD"):
            cmd.append("--reload")
    else:
        cmd.extend(["--log-level", "warning"])

    log.info(f"Starting hypercorn: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, env=env)
    except KeyboardInterrupt:
        log.info("Server stopped by user")
    except Exception as e:
        log.error(f"Error running hypercorn: {e}")
        sys.exit(1)


@click.command()
@click.option(
    "--server",
    type=click.Choice(["uvicorn", "hypercorn"]),
    default="uvicorn",
    help="ASGI server to use",
)
@click.option("--debug", is_flag=True, help="Debug mode")
@click.option("--more", is_flag=True, help="Debug mode with more verbosity")
@click.option("--unminified", is_flag=True, help="Use the unminified js (for development only)")
@click.option("--host", default="localhost", help="Server host")
@click.option("--port", type=int, default=57575, help="Server port")
@click.option(
    "--keepalive-interval",
    "keepalive_interval",
    type=int,
    default=30,
    help="Interval between ping packets sent from server to client (in seconds)",
)
@click.option(
    "--one-shot",
    "one_shot",
    is_flag=True,
    help="Run a one-shot instance. Quit at term close",
)
@click.option("--shell", help="Shell to execute at login")
@click.option("--motd", default="motd", help="Path to the motd file.")
@click.option("--cmd", help='Command to run instead of shell, f.i.: "ls -l"')
@click.option("--unsecure", is_flag=True, help="Don't use ssl not recommended")
@click.option(
    "--i-hereby-declare-i-dont-want-any-security-whatsoever",
    "i_hereby_declare_i_dont_want_any_security_whatsoever",
    is_flag=True,
    help="Remove all security and warnings. There are some use cases for that. Use this if you really know what you are doing.",
)
@click.option("--login", is_flag=True, help="Use login screen at start")
@click.option(
    "--pam-profile",
    "pam_profile",
    type=str,
    default="",
    help="When --login=True provided and running as ROOT, use PAM with the specified PAM profile for authentication and then execute the user's default shell. Will override --shell.",
)
@click.option(
    "--force-unicode-width",
    "force_unicode_width",
    is_flag=True,
    help="Force all unicode characters to the same width. Useful for avoiding layout mess.",
)
@click.option("--ssl-version", "ssl_version", help="SSL protocol version")
@click.option(
    "--generate-certs",
    "generate_certs",
    is_flag=True,
    help="Generate aetherterm certificates",
)
@click.option(
    "--generate-current-user-pkcs",
    "generate_current_user_pkcs",
    is_flag=True,
    help="Generate current user pfx for client authentication",
)
@click.option(
    "--generate-user-pkcs",
    "generate_user_pkcs",
    default="",
    help="Generate user pkcs for client authentication (Must be root to create for another user)",
)
@click.option(
    "--uri-root-path",
    "uri_root_path",
    default="",
    help="Sets the server root path: example.com/<uri_root_path>/static/",
)
@click.option(
    "--ai-mode",
    "ai_mode",
    default="streaming",
    type=click.Choice(["streaming", "sentence_by_sentence", "disabled"]),
    help="Sets the AI assistance mode (streaming, sentence_by_sentence, or disabled).",
)
def main(**kwargs):
    """AetherTerm AgentServer - A sleek web based terminal emulator."""
    log.info("Starting AetherTerm AgentServer...")

    # SSL certificates should be prepared beforehand using:
    # aetherterm-ssl-setup --host=<host> --port=<port>
    if not kwargs.get("unsecure", False):
        log.info("Using HTTPS mode - ensure SSL certificates are prepared")
    else:
        log.info("Using HTTP mode (unsecure)")

    # Show URL
    protocol = "https" if not kwargs.get("unsecure", False) else "http"
    host = kwargs.get("host", "localhost")
    port = kwargs.get("port", 57575)
    uri_root_path = kwargs.get("uri_root_path", "").strip("/")
    url = f"{protocol}://{host}:{port}/{uri_root_path + '/' if uri_root_path else ''}"
    log.info(f"AetherTerm AgentServer is ready, open your browser to: {url}")

    # Launch with selected server
    server = kwargs.get("server", "uvicorn")
    if server == "uvicorn":
        launch_uvicorn(kwargs)
    else:
        launch_hypercorn(kwargs)


if __name__ == "__main__":
    main()

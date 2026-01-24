#!/usr/bin/env python

import asyncio
import logging

import click

from aetherterm.agentserver import start_server

# Configure logging for the launcher script
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("butterfly.launcher")
@click.command()
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
    help="Generate butterfly certificates",
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
    help="Generate user pfx for client authentication (Must be root to create for another user)",
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
    """Butterfly - A sleek web based terminal emulator."""
    log.info("Starting Butterfly server...")

    # Run the async server
    asyncio.run(start_server(**kwargs))
if __name__ == "__main__":
    main()

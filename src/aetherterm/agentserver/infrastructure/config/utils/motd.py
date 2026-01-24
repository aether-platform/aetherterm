"""
MOTD (Message of the Day) utilities for AetherTerm AgentServer.
"""

import os
from logging import getLogger

log = getLogger("aetherterm.agentserver.utils.motd")
class AnsiColors:
    colors = {
        "black": 30,
        "red": 31,
        "green": 32,
        "yellow": 33,
        "blue": 34,
        "magenta": 35,
        "cyan": 36,
        "white": 37,
    }

    def __getattr__(self, key):
        bold = True
        if key.startswith("light_"):
            bold = False
            key = key[len("light_") :]
        if key in self.colors:
            return "\x1b[%d%sm" % (self.colors[key], ";1" if bold else "")
        if key == "reset":
            return "\x1b[0m"
        return ""
ansi_colors = AnsiColors()
def render_motd(
    socket, user, uri, unsecure=False, i_hereby_declare_i_dont_want_any_security_whatsoever=False
):
    """
    Render the MOTD (Message of the Day) template with Jinja2.

    Args:
        socket: Connection socket information
        user: User information
        uri: Connection URI
        unsecure: Whether the connection is unsecure
        i_hereby_declare_i_dont_want_any_security_whatsoever: Security override flag

    Returns:
        Rendered MOTD string
    """
    from jinja2 import Environment, FileSystemLoader

    from aetherterm.agentserver.__about__ import __version__

    # Get template directory
    template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")

    # Create Jinja2 environment
    env = Environment(loader=FileSystemLoader(template_dir))

    # Load MOTD template
    try:
        template = env.get_template("motd.j2")
    except Exception as e:
        log.error(f"Failed to load MOTD template: {e}")
        return ""

    # Create opts object
    opts = type(
        "Options",
        (),
        {
            "unsecure": unsecure,
            "i_hereby_declare_i_dont_want_any_security_whatsoever": i_hereby_declare_i_dont_want_any_security_whatsoever,
        },
    )()

    # Create butterfly object with socket info including proxy_addr
    butterfly_obj = type(
        "Butterfly",
        (),
        {
            "socket": type(
                "Socket",
                (),
                {
                    "local_addr": getattr(socket, "local_addr", "localhost"),
                    "local_port": getattr(socket, "local_port", 8080),
                    "remote_addr": getattr(socket, "remote_addr", "127.0.0.1"),
                    "remote_port": getattr(socket, "remote_port", 0),
                    "proxy_addr": getattr(socket, "proxy_addr", None),
                },
            )()
        },
    )()

    # Prepare template context
    context = {
        "colors": ansi_colors,
        "version": __version__,
        "aetherterm": butterfly_obj,
        "butterfly": butterfly_obj,  # Add butterfly alias for backward compatibility
        "opts": opts,
        "uri": uri,
    }

    try:
        # Render template
        rendered = template.render(**context)
        log.debug(f"MOTD rendered successfully: {len(rendered)} characters")
        return rendered
    except Exception as e:
        log.error(f"Failed to render MOTD template: {e}")
        import traceback

        log.error(traceback.format_exc())
        return ""

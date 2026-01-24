# This file is part of butterfly
#
# butterfly Copyright(C) 2015-2017 Florian Mounier
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

import os
import pwd
import re
import subprocess
import sys
from logging import getLogger

log = getLogger("aetherterm.agentserver")
def get_hex_ip_port(remote):
    ip, port = remote
    if ip.startswith("::ffff:"):
        ip = ip[len("::ffff:") :]
    splits = ip.split(".")
    if ":" not in ip and len(splits) == 4:
        # Must be an ipv4
        return "%02X%02X%02X%02X:%04X" % (
            int(splits[3]),
            int(splits[2]),
            int(splits[1]),
            int(splits[0]),
            int(port),
        )
    try:
        import ipaddress
    except ImportError:
        print("Please install ipaddress backport for ipv6 user detection")
        return ""

    # Endian reverse:
    ipv6_parts = ipaddress.IPv6Address(ip).exploded.split(":")
    for i in range(0, 8, 2):
        ipv6_parts[i], ipv6_parts[i + 1] = (
            ipv6_parts[i + 1][2:] + ipv6_parts[i + 1][:2],
            ipv6_parts[i][2:] + ipv6_parts[i][:2],
        )

    return "".join(ipv6_parts) + ":%04X" % port
def parse_cert(cert):
    user = None

    for elt in cert["subject"]:
        user = dict(elt).get("commonName", None)
        if user:
            break

    return user
class User:
    def __init__(self, uid=None, name=None):
        if uid is None and not name:
            uid = os.getuid()
        if uid is not None:
            self.pw = pwd.getpwuid(uid)
        else:
            self.pw = pwd.getpwnam(name)
        if self.pw is None:
            raise LookupError("Unknown user")

    @property
    def uid(self):
        return self.pw.pw_uid

    @property
    def gid(self):
        return self.pw.pw_gid

    @property
    def name(self):
        return self.pw.pw_name

    @property
    def dir(self):
        return self.pw.pw_dir

    @property
    def shell(self):
        return self.pw.pw_shell

    @property
    def root(self):
        return self.uid == 0

    def __eq__(self, other):
        if other is None:
            return False
        return self.uid == other.uid

    def __repr__(self):
        return "%s [%r]" % (self.name, self.uid)
class ConnectionInfo:
    """Connection information for Socket.IO and other non-socket connections."""

    def __init__(self, environ=None, socket_remote_addr=None):
        if environ is None:
            environ = {}

        # Get client address from headers (X-Real-IP, X-Forwarded-For)
        header_remote_addr = (
            environ.get("HTTP_X_REAL_IP")
            or environ.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        )

        # If we have both header and socket remote addresses and they differ,
        # use header as remote_addr and socket as proxy_addr
        if header_remote_addr and socket_remote_addr and header_remote_addr != socket_remote_addr:
            self.remote_addr = header_remote_addr
            self.proxy_addr = socket_remote_addr
        else:
            # Use header if available, otherwise socket, otherwise default
            self.remote_addr = (
                header_remote_addr or socket_remote_addr or environ.get("REMOTE_ADDR", "127.0.0.1")
            )
            self.proxy_addr = None

        # Try to get remote port from various sources
        self.remote_port = int(environ.get("REMOTE_PORT", 0))
        if self.remote_port == 0:
            # Try to extract port from HTTP_HOST or other headers
            host_header = environ.get("HTTP_HOST", "")
            if ":" in host_header:
                try:
                    self.remote_port = int(host_header.split(":")[1])
                except (ValueError, IndexError):
                    pass

        # Server address info
        self.local_addr = environ.get("SERVER_NAME", "127.0.0.1")
        self.local_port = int(environ.get("SERVER_PORT", 57575))

        self.user = None
        self.env = {}

    @property
    def local(self):
        return (
            self.remote_addr in ["127.0.0.1", "::1", "::ffff:127.0.0.1"]
            or self.local_addr == self.remote_addr
        )

    def __repr__(self):
        proxy_info = f" Proxy: {self.proxy_addr}" if self.proxy_addr else ""
        return "<ConnectionInfo L: %s:%d R: %s:%d%s User: %r>" % (
            self.local_addr,
            self.local_port,
            self.remote_addr,
            self.remote_port,
            proxy_info,
            self.user,
        )
class Socket:
    def __init__(self, socket):
        sn = socket.getsockname()
        self.local_addr = sn[0]
        self.local_port = sn[1]
        try:
            pn = socket.getpeername()
            self.remote_addr = pn[0]
            self.remote_port = pn[1]
        except Exception:
            log.debug("Can't get peer name", exc_info=True)
            self.remote_addr = "???"
            self.remote_port = 0
        self.user = None
        self.env = {}

        if not self.local:
            return

        # If there is procfs, get as much info as we can
        if os.path.exists("/proc/net"):
            try:
                line = get_procfs_socket_line(get_hex_ip_port(pn[:2]))
                self.user = User(uid=int(line[7]))
                self.env = get_socket_env(line[9], self.user)
            except Exception:
                log.debug("procfs was no good, aight", exc_info=True)

        if self.user is None:
            # Try with lsof
            try:
                self.user = User(name=get_lsof_socket_line(self.remote_addr, self.remote_port)[1])
            except Exception:
                log.debug("lsof was no good", exc_info=True)

    @property
    def local(self):
        return (
            self.remote_addr in ["127.0.0.1", "::1", "::ffff:127.0.0.1"]
            or self.local_addr == self.remote_addr
        )

    def __repr__(self):
        return "<Socket L: %s:%d R: %s:%d User: %r>" % (
            self.local_addr,
            self.local_port,
            self.remote_addr,
            self.remote_port,
            self.user,
        )
# Portable way to get the user, if lsof is installed
def get_lsof_socket_line(addr, port):
    # May want to make this into a dictionary in the future...
    regex = (
        r"\w+\s+(?P<pid>\d+)\s+(?P<user>\w+).*\s"
        r"(?P<laddr>.*?):(?P<lport>\d+)->(?P<raddr>.*?):(?P<rport>\d+)"
    )
    output = subprocess.check_output(["lsof", "-Pni"]).decode("utf-8")
    lines = output.split("\n")
    for line in lines:
        # Look for local address with peer port
        match = re.findall(regex, line)
        if len(match):
            match = match[0]
            if int(match[5]) == port:
                return match
    raise Exception("Couldn't find a match!")
# Linux only socket line get
def get_procfs_socket_line(hex_ip_port):
    fn = None
    if len(hex_ip_port) == 13:  # ipv4
        fn = "/proc/net/tcp"
    elif len(hex_ip_port) == 37:  # ipv6
        fn = "/proc/net/tcp6"
    if not fn:
        return None
    try:
        with open(fn) as k:
            lines = k.readlines()
        for line in lines:
            # Look for local address with peer port
            if line.split()[1] == hex_ip_port:
                # We got the socket
                return line.split()
    except Exception:
        log.debug("getting socket %s line fail" % fn, exc_info=True)
# Linux only browser environment far fetch
def get_socket_env(inode, user):
    for pid in os.listdir("/proc/"):
        if not pid.isdigit():
            continue
        try:
            with open("/proc/%s/cmdline" % pid) as c:
                command = c.read().split("\x00")
                executable = command[0].split("/")[-1]
                if executable in ("sh", "bash", "zsh"):
                    executable = command[1].split("/")[-1]
                if executable in [
                    "gnome-session",
                    "gnome-session-binary",
                    "startkde",
                    "startdde",
                    "xfce4-session",
                ]:
                    with open("/proc/%s/status" % pid) as e:
                        uid = None
                        for line in e.read().splitlines():
                            parts = line.split("\t")
                            if parts[0] == "Uid:":
                                uid = int(parts[1])
                                break
                        if not uid or uid != user.uid:
                            continue

                    with open("/proc/%s/environ" % pid) as e:
                        keyvals = e.read().split("\x00")
                        env = {}
                        for keyval in keyvals:
                            if "=" in keyval:
                                key, val = keyval.split("=", 1)
                                env[key] = val
                        return env
        except Exception:
            continue

    for pid in os.listdir("/proc/"):
        if not pid.isdigit():
            continue
        for fd in os.listdir("/proc/%s/fd/" % pid):
            lnk = "/proc/%s/fd/%s" % (pid, fd)
            if not os.path.islink(lnk):
                continue
            if "socket:[%s]" % inode == os.readlink(lnk):
                with open("/proc/%s/status" % pid) as s:
                    for line in s.readlines():
                        if line.startswith("PPid:"):
                            with open("/proc/%s/environ" % line[len("PPid:") :].strip()) as e:
                                keyvals = e.read().split("\x00")
                                env = {}
                                for keyval in keyvals:
                                    if "=" in keyval:
                                        key, val = keyval.split("=", 1)
                                        env[key] = val
                                return env
def add_user_info(id, fd, pid, user, host):
    """Legacy function - no longer needed for modern systems."""
    pass
def rm_user_info(id, pid):
    """Legacy function - no longer needed for modern systems."""
    pass
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
    import os

    from jinja2 import Environment, FileSystemLoader

    from aetherterm.agentserver.__about__ import __version__

    # Get template directory
    template_dir = os.path.join(os.path.dirname(__file__), "templates")

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

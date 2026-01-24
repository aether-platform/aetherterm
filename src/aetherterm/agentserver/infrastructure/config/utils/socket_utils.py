"""
Socket and connection utilities for AetherTerm AgentServer.
"""

import os
from logging import getLogger

log = getLogger("aetherterm.agentserver.utils.socket_utils")
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
        from .system_utils import get_lsof_socket_line, get_procfs_socket_line, get_socket_env
        from .user_management import User

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

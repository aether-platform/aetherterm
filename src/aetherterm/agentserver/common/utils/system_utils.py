"""System utilities for AetherTerm AgentServer."""

import os
import re
import subprocess
from logging import getLogger

log = getLogger("aetherterm.agentserver.utils.system_utils")


def get_lsof_socket_line(addr, port):
    """Portable way to get the user, if lsof is installed."""
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


def get_procfs_socket_line(hex_ip_port):
    """Linux only socket line get."""
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


def get_socket_env(inode, user):
    """Linux only browser environment far fetch."""
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

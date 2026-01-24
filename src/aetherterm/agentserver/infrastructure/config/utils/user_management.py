"""
User management utilities for AetherTerm AgentServer.
"""

import os
import pwd
import sys
from logging import getLogger

log = getLogger("aetherterm.agentserver.utils.user_management")
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
def add_user_info(id, fd, pid, user, host):
    """Add user information to system logs."""
    if sys.platform != "linux":
        return
    # utmp/wtmp functionality is currently disabled
def rm_user_info(id, pid):
    """Remove user information from system logs."""
    if sys.platform != "linux":
        return
    # utmp/wtmp functionality is currently disabled

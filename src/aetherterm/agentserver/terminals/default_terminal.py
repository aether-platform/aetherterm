# This file is part of aetherterm
#
# Copyright 2025 Florian Mounier
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import fcntl
import os
import pty
import random
import signal
import string
import struct
import sys
import termios
from logging import getLogger

import tornado.ioloop
import tornado.options
import tornado.process
import tornado.web
import tornado.websocket

from aetherterm import __version__, utils

from .base_terminal import BaseTerminal

log = getLogger("aetherterm")
ioloop = tornado.ioloop.IOLoop.instance()
server = utils.User()
daemon = utils.User(name="daemon")


# Python 2 backward compatibility
try:
    input = raw_input
except NameError:
    pass


class DefaultTerminal(BaseTerminal):
    sessions = {}

    def __init__(self, user, path, session, socket, uri, render_string, broadcast):
        self.sessions[session] = self
        self.history_size = 50000
        self.history = ""
        self.uri = uri
        self.session = session
        self.broadcast = broadcast
        self.fd = None
        self.closed = False
        self.socket = socket
        log.info("Terminal opening with session: %s and socket %r" % (self.session, self.socket))
        self.path = path
        self.user = user if user else None
        self.caller = self.callee = None

        # If local we have the user connecting
        if self.socket.local and self.socket.user is not None:
            self.caller = self.socket.user

        if tornado.options.options.unsecure:
            if self.user:
                try:
                    self.callee = self.user
                except LookupError:
                    log.debug("Can't switch to user %s" % self.user, exc_info=True)
                    self.callee = None

            # If no user where given and we are local, keep the same
            # user as the one who opened the socket ie: the one
            # openning a terminal in browser
            if not self.callee and not self.user and self.socket.local:
                self.user = self.callee = self.caller
        else:
            # Authed user
            self.callee = self.user

        if tornado.options.options.motd != "":
            motd = (
                render_string(
                    tornado.options.options.motd,
                    aetherterm=self,
                    version=__version__,
                    opts=tornado.options.options,
                    uri=self.uri,
                    colors=utils.ansi_colors,
                )
                .decode("utf-8")
                .replace("\r", "")
                .replace("\n", "\r\n")
            )
            self.send(motd)

        log.info("Forking pty for user %r" % self.user)

    def send(self, message):
        if message is not None:
            self.history += message
            if len(self.history) > self.history_size:
                self.history = self.history[-self.history_size :]
        self.broadcast(self.session, message)

    def pty(self):
        # Make a "unique" id in 4 bytes
        self.uid = "".join(
            random.choice(string.ascii_lowercase + string.ascii_uppercase + string.digits)
            for _ in range(4)
        )

        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            self.determine_user()
            log.debug(
                "Pty forked for user %r caller %r callee %r" % (self.user, self.caller, self.callee)
            )
            self.shell()
        else:
            self.communicate()

    def determine_user(self):
        if not tornado.options.options.unsecure:
            # Secure mode we must have already a callee
            assert self.callee is not None
            return

        # If we should login, login
        if tornado.options.options.login:
            user = ""
            while user == "":
                try:
                    user = input("login: ")
                except (KeyboardInterrupt, EOFError):
                    log.debug("Error in login input", exc_info=True)

            try:
                self.callee = utils.User(name=user)
            except Exception:
                log.debug("Can't switch to user %s" % user, exc_info=True)
                self.callee = utils.User(name="nobody")
            return

        # if login is not required, we will use the same user as
        # aetherterm is executed
        self.callee = self.callee or utils.User()

    def shell(self):
        try:
            os.chdir(self.path or self.callee.dir)
        except Exception:
            log.debug("Can't chdir to %s" % (self.path or self.callee.dir), exc_info=True)

        # If local and local user is the same as login user
        # We set the env of the user from the browser
        # Usefull when running as root
        if self.caller == self.callee:
            env = os.environ
            env.update(self.socket.env)
        else:
            # May need more?
            env = {}
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "aetherterm"
        env["HOME"] = self.callee.dir
        env["LOCATION"] = self.uri
        env["AETHERTERM_PATH"] = os.path.abspath(os.path.join(os.path.dirname(__file__), "bin"))

        try:
            tty = os.ttyname(0).replace("/dev/", "")
        except Exception:
            log.debug("Can't get ttyname", exc_info=True)
            tty = ""
        if self.caller != self.callee:
            try:
                os.chown(os.ttyname(0), self.callee.uid, -1)
            except Exception:
                log.debug("Can't chown ttyname", exc_info=True)

        utils.add_user_info(self.uid, tty, os.getpid(), self.callee.name, self.uri)

        local_login = self.socket.local and self.caller == self.callee and server == self.callee
        secure = not tornado.options.options.unsecure
        force_login = tornado.options.options.login
        ignore_security = (
            tornado.options.options.i_hereby_declare_i_dont_want_any_security_whatsoever
        )

        if not force_login and (ignore_security or secure or local_login):
            # User has been auth with ssl or is the same user as server
            # or login is explicitly turned off
            if secure and not local_login:
                # User is authed by ssl, setting groups
                try:
                    os.initgroups(self.callee.name, self.callee.gid)
                    os.setgid(self.callee.gid)
                    os.setuid(self.callee.uid)
                    # Apparently necessary for some cmd
                    env["LOGNAME"] = env["USER"] = self.callee.name
                except Exception:
                    log.error(
                        "The server must be run as root if you want to log as different user\n",
                        exc_info=True,
                    )
                    sys.exit(1)

            if tornado.options.options.cmd:
                args = tornado.options.options.cmd.split(" ")
            else:
                args = [tornado.options.options.shell or self.callee.shell]
                args.append("-il")

            # In some cases some shells don't export SHELL var
            env["SHELL"] = args[0]
            os.execvpe(args[0], args, env)
            # This process has been replaced

        if tornado.options.options.pam_profile:
            if not server.root:
                print("You must be root to use pam_profile option.")
                sys.exit(3)
            pam_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "pam.py")
            os.execvpe(
                sys.executable,
                [
                    sys.executable,
                    pam_path,
                    self.callee.name,
                    tornado.options.options.pam_profile,
                ],
                env,
            )

        # Unsecure connection with su
        if server.root:
            if self.socket.local:
                if self.callee != self.caller:
                    # Force password prompt by dropping rights
                    # to the daemon user
                    os.setuid(daemon.uid)
            else:
                # We are not local so we should always get a password prompt
                if self.callee == daemon:
                    # No logging from daemon
                    sys.exit(1)
                os.setuid(daemon.uid)

        if os.path.exists("/usr/bin/su"):
            args = ["/usr/bin/su"]
        else:
            args = ["/bin/su"]

        args.append("-l")
        if sys.platform.startswith("linux") and tornado.options.options.shell:
            args.append("-s")
            args.append(tornado.options.options.shell)
        args.append(self.callee.name)
        os.execvpe(args[0], args, env)

    def communicate(self):
        fcntl.fcntl(self.fd, fcntl.F_SETFL, os.O_NONBLOCK)

        def utf8_error(e):
            log.error(e)

        self.reader = open(self.fd, "rb", buffering=0, closefd=False)
        self.writer = open(self.fd, "w", encoding="utf-8", closefd=False)
        ioloop.add_handler(self.fd, self.shell_handler, ioloop.READ | ioloop.ERROR)

    def write(self, message):
        if not hasattr(self, "writer"):
            self.on_close()
            self.close()

        log.debug("WRIT<%r" % message)
        self.writer.write(message)
        self.writer.flush()

    def ctl(self, message):
        if message["cmd"] == "size":
            cols = message["cols"]
            rows = message["rows"]
            s = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, s)
            log.info("SIZE (%d, %d)" % (cols, rows))

    def shell_handler(self, fd, events):
        if events & ioloop.READ:
            try:
                read = self.reader.read()
            except OSError:
                read = ""

            log.debug("READ>%r" % read)
            if read and len(read) != 0:
                self.send(read.decode("utf-8", "replace"))
            else:
                events = ioloop.ERROR

        if events & ioloop.ERROR:
            log.info("Error on fd %d, closing" % fd)
            # Terminated
            self.send(None)  # Close all
            self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.fd is not None:
            log.info("Closing fd %d" % self.fd)

        if getattr(self, "pid", 0) == 0:
            log.info("pid is 0")
            return

        utils.rm_user_info(self.uid, self.pid)

        try:
            ioloop.remove_handler(self.fd)
        except Exception:
            log.error("handler removal fail", exc_info=True)

        try:
            os.close(self.fd)
        except Exception:
            log.debug("closing fd fail", exc_info=True)

        try:
            os.kill(self.pid, signal.SIGHUP)
            os.kill(self.pid, signal.SIGCONT)
            os.waitpid(self.pid, 0)
        except Exception:
            log.debug("waitpid fail", exc_info=True)

        del self.sessions[self.session]

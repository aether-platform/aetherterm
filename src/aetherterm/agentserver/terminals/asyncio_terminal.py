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

import asyncio
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

from aetherterm.agentserver import utils

from .base_terminal import BaseTerminal

log = getLogger("aetherterm.terminal")


class AsyncioTerminal(BaseTerminal):
    sessions = {}
    closed_sessions = set()  # Track closed session IDs
    session_owners = {}  # Track session owners: {session_id: user_info}

    def __init__(
        self, user, path, session, socket, uri, render_string, broadcast, login, pam_profile
    ):
        self.sessions[session] = self
        self.history_size = 50000
        self.history = ""
        self.uri = uri
        self.session = session
        self.broadcast = broadcast
        self.fd = None
        self.closed = False
        self.socket = socket
        self.process = None
        self.reader_task = None
        self.client_sids = set()  # Track multiple clients for this session

        # Store session owner information
        owner_info = {
            "remote_addr": socket.remote_addr if socket else None,
            "remote_user": socket.env.get("HTTP_X_REMOTE_USER") if socket and socket.env else None,
            "user_name": user.name if user else None,
            "created_at": __import__("time").time(),
        }
        self.session_owners[session] = owner_info

        log.info("Terminal opening with session: %s and socket %r" % (self.session, self.socket))
        self.path = path
        self.user = user if user else None
        self.caller = self.callee = None

        # If local we have the user connecting
        if self.socket.local and self.socket.user is not None:
            self.caller = self.socket.user

        # User determination logic (simplified for asyncio version)
        if self.user:
            try:
                self.callee = self.user
            except LookupError:
                log.debug("Can't switch to user %s" % self.user, exc_info=True)
                self.callee = None

        # If no user where given and we are local, keep the same
        # user as the one who opened the socket
        if not self.callee and not self.user and self.socket.local:
            self.user = self.callee = self.caller

        # Default to current user if no specific user
        self.callee = self.callee or utils.User()
        self.login = login
        self.pam_profile = pam_profile

        log.info("Forking pty for user %r" % self.user)

    def send(self, message):
        """Send message to all connected clients."""
        if message is not None:
            self.history += message
            if len(self.history) > self.history_size:
                self.history = self.history[-self.history_size :]
        self.broadcast(self.session, message)

    async def start_pty(self):
        """Start the PTY process using asyncio."""
        # Make a "unique" id in 4 bytes
        self.uid = "".join(
            random.choice(string.ascii_lowercase + string.ascii_uppercase + string.digits)
            for _ in range(4)
        )

        # Create PTY
        master_fd, slave_fd = pty.openpty()
        self.fd = master_fd

        # Set up environment
        env = self._setup_environment()

        # Determine shell command
        shell_cmd = await self._get_shell_command()

        try:
            # Fork process manually since asyncio.create_subprocess_exec doesn't work well with PTY
            pid = os.fork()

            if pid == 0:
                # Child process
                os.close(master_fd)  # Close master in child

                # Make slave the controlling terminal
                os.setsid()
                os.dup2(slave_fd, 0)  # stdin
                os.dup2(slave_fd, 1)  # stdout
                os.dup2(slave_fd, 2)  # stderr
                os.close(slave_fd)

                # Change to target directory
                try:
                    os.chdir(self.path or self.callee.dir)
                except Exception:
                    pass

                # Set up environment and execute shell
                os.execvpe(shell_cmd[0], shell_cmd, env)
            else:
                # Parent process
                self.pid = pid
                os.close(slave_fd)  # Close slave in parent

                # Set master fd to non-blocking
                fcntl.fcntl(master_fd, fcntl.F_SETFL, os.O_NONBLOCK)

                # Start reading from PTY
                self.reader_task = asyncio.create_task(self._read_from_pty())

                # Send MOTD for new sessions after a delay to allow shell initialization
                if len(self.client_sids) == 1:  # This is the first client for this session
                    asyncio.create_task(self._delayed_motd_send())

                log.info(f"PTY started with PID {pid}")

        except Exception as e:
            log.error(f"Failed to start PTY: {e}")
            try:
                os.close(slave_fd)
            except:
                pass
            try:
                os.close(master_fd)
            except:
                pass
            raise

    def _setup_environment(self):
        """Set up environment variables for the shell."""
        # If local and local user is the same as login user
        # We set the env of the user from the browser
        if self.caller == self.callee:
            env = os.environ.copy()
            env.update(self.socket.env)
        else:
            env = {}

        env.update(
            {
                "TERM": "xterm-256color",
                "COLORTERM": "aetherterm",
                "HOME": self.callee.dir,
                "LOCATION": self.uri,
                "BUTTERFLY_PATH": os.path.abspath(
                    os.path.join(os.path.dirname(__file__), "..", "bin")
                ),
                "SHELL": self.callee.shell,
            }
        )

        return env

    async def _get_shell_command(self):
        """Get the shell command to execute.

        Always launches the OS shell directly.
        AgentShell connects as an independent ZMQ observer (not in the PTY chain).
        """
        if self.login:
            # If login is enabled, we need to handle PAM authentication
            if self.pam_profile:
                # Use PAM for authentication
                pam_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "pam.py")
                return [
                    sys.executable,
                    pam_path,
                    self.callee.name,
                    self.pam_profile,
                ]
            # Fallback to su if PAM profile is not specified
            if os.path.exists("/usr/bin/su"):
                args = ["/usr/bin/su"]
            else:
                args = ["/bin/su"]
            args.append("-l")
            args.append(self.callee.name)
            return args
        # If login is not required, use the user's default shell
        return [self.callee.shell, "-il"]

    def _setup_child_process(self):
        """Setup function called in child process before exec."""
        try:
            # Set process group
            os.setsid()

            # Add user info for tracking
            try:
                tty = os.ttyname(0).replace("/dev/", "")
            except Exception:
                tty = ""

            utils.add_user_info(self.uid, tty, os.getpid(), self.callee.name, self.uri)

        except Exception as e:
            log.error(f"Error in child process setup: {e}")

    async def _read_from_pty(self):
        """Continuously read from PTY and send to clients."""
        try:
            while not self.closed:
                try:
                    # Check if child process is still alive
                    if hasattr(self, "pid"):
                        try:
                            pid, status = os.waitpid(self.pid, os.WNOHANG)
                            if pid != 0:  # Process has exited
                                log.info(f"Child process {self.pid} exited with status {status}")
                                break
                        except OSError:
                            # Process doesn't exist anymore
                            break

                    # Read from PTY with timeout
                    data = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(None, self._read_pty_data),
                        timeout=0.1,
                    )

                    if data:
                        # Decode and send to clients
                        try:
                            text = data.decode("utf-8", "replace")
                            self.send(text)
                        except Exception as e:
                            log.error(f"Error decoding PTY data: {e}")

                except asyncio.TimeoutError:
                    # No data available, continue
                    continue
                except Exception as e:
                    log.error(f"Error reading from PTY: {e}")
                    break

        except Exception as e:
            log.error(f"PTY reader task error: {e}")
        finally:
            await self.close()

    def _read_pty_data(self):
        """Read data from PTY (blocking operation for executor)."""
        try:
            return os.read(self.fd, 4096)
        except OSError:
            return b""

    async def write(self, message):
        """Write message to PTY."""
        if self.closed or not self.fd:
            return

        try:
            log.debug("WRIT<%r" % message)
            # Write to PTY
            await asyncio.get_event_loop().run_in_executor(
                None, os.write, self.fd, message.encode("utf-8")
            )
        except Exception as e:
            log.error(f"Error writing to PTY: {e}")
            await self.close()

    async def resize(self, cols, rows):
        """Resize the PTY."""
        if self.closed or not self.fd:
            return

        try:
            s = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, s)
            log.info("SIZE (%d, %d)" % (cols, rows))
        except Exception as e:
            log.error(f"Error resizing PTY: {e}")

    async def close(self):
        """Close the terminal and clean up resources."""
        if self.closed:
            return

        self.closed = True
        log.info("Closing terminal session %s" % self.session)

        # Cancel reader task
        if self.reader_task and not self.reader_task.done():
            self.reader_task.cancel()
            try:
                await self.reader_task
            except asyncio.CancelledError:
                pass

        # Close PTY file descriptor
        if self.fd is not None:
            try:
                os.close(self.fd)
            except Exception as e:
                log.debug(f"Error closing PTY fd: {e}")

        # Terminate process
        if hasattr(self, "pid"):
            try:
                # Send SIGTERM first
                os.kill(self.pid, signal.SIGTERM)

                # Wait a bit for graceful termination
                for _ in range(50):  # Wait up to 5 seconds
                    try:
                        pid, status = os.waitpid(self.pid, os.WNOHANG)
                        if pid != 0:  # Process has exited
                            break
                    except OSError:
                        # Process doesn't exist anymore
                        break
                    await asyncio.sleep(0.1)
                else:
                    # Force kill if still alive
                    try:
                        os.kill(self.pid, signal.SIGKILL)
                        os.waitpid(self.pid, 0)
                    except OSError:
                        pass

            except Exception as e:
                log.error(f"Error terminating process: {e}")

        # Clean up user info
        if hasattr(self, "uid") and hasattr(self, "pid"):
            try:
                utils.rm_user_info(self.uid, self.pid)
            except Exception as e:
                log.debug(f"Error removing user info: {e}")

        # Remove from sessions and add to closed sessions
        if self.session in self.sessions:
            del self.sessions[self.session]

        # Track this session as closed (keep owner info for ownership checking)
        self.closed_sessions.add(self.session)
        # Note: We keep session_owners[self.session] for ownership checking

        # Notify clients that terminal is closed
        self.send(None)

    async def _delayed_motd_send(self):
        """Send MOTD after shell initialization is complete."""
        try:
            # Wait for shell to initialize (adjust timing as needed)
            await asyncio.sleep(2.0)
            await self._send_motd_direct()
        except Exception as e:
            log.error(f"Failed to send delayed MOTD: {e}")

    async def _send_motd_direct(self):
        """Send MOTD (Message of the Day) directly to socket before shell starts."""
        try:
            from aetherterm.agentserver.containers import ApplicationContainer
            from aetherterm.agentserver.utils import render_motd

            # Get configuration from DI container
            try:
                # Try to get injected values, fallback to defaults if not available
                unsecure = getattr(ApplicationContainer.config, "unsecure", lambda: False)()
                i_hereby_declare = getattr(
                    ApplicationContainer.config,
                    "i_hereby_declare_i_dont_want_any_security_whatsoever",
                    lambda: False,
                )()
            except:
                # Fallback to defaults if DI is not available
                unsecure = False
                i_hereby_declare = False

            # Render MOTD
            motd_content = render_motd(
                socket=self.socket,
                user=self.callee,
                uri=self.uri,
                unsecure=unsecure,
                i_hereby_declare_i_dont_want_any_security_whatsoever=i_hereby_declare,
            )

            if motd_content:
                # Send MOTD directly to socket (not to PTY)
                # This will appear in the terminal before the shell starts
                # Convert line endings to proper terminal format
                motd_content = motd_content.replace("\n", "\r\n")
                if not motd_content.endswith("\r\n"):
                    motd_content += "\r\n"
                self.send(motd_content)
                log.info("MOTD sent directly to socket")
            else:
                log.warning("MOTD content is empty")

        except Exception as e:
            log.error(f"Failed to send MOTD directly: {e}")
            import traceback

            log.error(traceback.format_exc())

    async def _send_motd(self):
        """Send MOTD (Message of the Day) to the terminal."""
        try:
            from aetherterm.agentserver.containers import ApplicationContainer
            from aetherterm.agentserver.utils import render_motd

            # Get configuration from DI container
            try:
                # Try to get injected values, fallback to defaults if not available
                unsecure = getattr(ApplicationContainer.config, "unsecure", lambda: False)()
                i_hereby_declare = getattr(
                    ApplicationContainer.config,
                    "i_hereby_declare_i_dont_want_any_security_whatsoever",
                    lambda: False,
                )()
            except:
                # Fallback to defaults if DI is not available
                unsecure = False
                i_hereby_declare = False

            # Render MOTD
            motd_content = render_motd(
                socket=self.socket,
                user=self.callee,
                uri=self.uri,
                unsecure=unsecure,
                i_hereby_declare_i_dont_want_any_security_whatsoever=i_hereby_declare,
            )

            if motd_content:
                # Write MOTD to PTY using echo command to properly handle ANSI escape sequences
                await asyncio.sleep(0.2)  # Small delay to ensure PTY is ready

                # Split motd content into lines and send each line with echo -e
                lines = motd_content.split("\n")
                for line in lines:
                    if line.strip():  # Skip empty lines
                        # Escape single quotes and use echo -e to interpret escape sequences
                        escaped_line = line.replace("'", "'\"'\"'")
                        echo_command = f"echo -e '{escaped_line}'\n"
                        await self.write(echo_command)
                        await asyncio.sleep(0.01)  # Small delay between lines
                    else:
                        # For empty lines, just send a newline
                        await self.write("echo\n")
                        await asyncio.sleep(0.01)

                log.info("MOTD sent to terminal using echo commands")
            else:
                log.warning("MOTD content is empty")

        except Exception as e:
            log.error(f"Failed to send MOTD: {e}")
            import traceback

            log.error(traceback.format_exc())

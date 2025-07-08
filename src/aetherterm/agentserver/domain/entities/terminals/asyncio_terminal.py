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
import json
import os
import pty
import random
import re
import signal
import string
import struct
import sys  # Import sys
import termios
import time
from datetime import datetime
from logging import getLogger
from typing import Dict, List, Optional

from aetherterm.agentserver.infrastructure.config import utils
from aetherterm.agentserver.short_term_memory_local import LocalShortTermAnalyzer

from .base_terminal import BaseTerminal

log = getLogger("aetherterm.terminal")


class AsyncioTerminal(BaseTerminal):
    sessions = {}
    closed_sessions = set()  # Track closed session IDs
    session_owners = {}  # Track session owners: {session_id: user_info}
    session_buffers = {}  # Persistent buffer storage: {session_id: buffer_data}

    # Log processing infrastructure
    log_buffer = []  # Global log buffer for all sessions
    log_processing_task = None  # Background task for log processing
    
    # Local short-term memory analyzer
    local_analyzer = None  # Shared across all sessions

    # Short-term memory management
    short_term_memory_manager = None  # Shared across all sessions
    log_patterns = {
        "error": [
            r"error|ERROR|Error",
            r"failed|FAILED|Failed",
            r"exception|EXCEPTION|Exception",
            r"fatal|FATAL|Fatal",
            r"panic|PANIC|Panic",
        ],
        "warning": [
            r"warning|WARNING|Warning",
            r"warn|WARN|Warn",
            r"deprecated|DEPRECATED|Deprecated",
        ],
        "info": [
            r"info|INFO|Info",
            r"notice|NOTICE|Notice",
            r"starting|Starting|STARTING",
            r"stopping|Stopping|STOPPING",
        ],
        "success": [
            r"success|SUCCESS|Success",
            r"complete|COMPLETE|Complete",
            r"done|DONE|Done",
            r"ok|OK|Ok",
        ],
    }
    processed_logs = []  # Processed and categorized logs
    log_subscribers = set()  # WebSocket clients subscribed to log updates

    def __init__(
        self, user, path, session, socket, uri, render_string, broadcast, login, pam_profile
    ):
        self.sessions[session] = self
        self.history_size = 500000  # Increased from 50KB to 500KB for better buffer capacity
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

        # Initialize persistent buffer storage for this session
        if session not in self.session_buffers:
            self.session_buffers[session] = {
                "lines": [],
                "max_lines": 5000,
                "created_at": __import__("time").time(),
                "last_updated": __import__("time").time()
            }

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

            # Update persistent buffer storage
            self._update_persistent_buffer(message)

            # Add to log buffer for processing
            self.add_to_log_buffer(message)

            # Chunk large messages to prevent WebSocket frame size issues
            MAX_CHUNK_SIZE = 65536  # 64KB chunks
            if len(message) > MAX_CHUNK_SIZE:
                for i in range(0, len(message), MAX_CHUNK_SIZE):
                    chunk = message[i:i + MAX_CHUNK_SIZE]
                    self.broadcast(self.session, chunk)
            else:
                self.broadcast(self.session, message)

    def _update_persistent_buffer(self, message):
        """Update the persistent buffer storage for this session."""
        try:
            if self.session not in self.session_buffers:
                log.warning(f"Session {self.session} not found in session_buffers, initializing...")
                self.session_buffers[self.session] = {
                    "lines": [],
                    "max_lines": 5000,
                    "created_at": __import__("time").time(),
                    "last_updated": __import__("time").time()
                }
            
            buffer_data = self.session_buffers[self.session]
            
            # Add new line to buffer
            buffer_line = {
                "content": message,
                "timestamp": __import__("time").time(),
                "type": "output"
            }
            
            buffer_data["lines"].append(buffer_line)
            buffer_data["last_updated"] = __import__("time").time()
            
            # Log buffer status periodically
            line_count = len(buffer_data["lines"])
            if line_count % 100 == 0:
                log.debug(f"Session {self.session} buffer now has {line_count} lines")
            
            # Trim buffer if it exceeds max lines
            max_lines = buffer_data.get("max_lines", 5000)
            if len(buffer_data["lines"]) > max_lines:
                excess = len(buffer_data["lines"]) - max_lines
                buffer_data["lines"] = buffer_data["lines"][excess:]
                log.debug(f"Trimmed {excess} lines from session {self.session} buffer")
                    
        except Exception as e:
            log.error(f"Error updating persistent buffer for session {self.session}: {e}", exc_info=True)

    @classmethod
    def get_session_buffer(cls, session_id: str) -> dict:
        """Get the persistent buffer for a session."""
        return cls.session_buffers.get(session_id, {
            "lines": [],
            "max_lines": 5000,
            "created_at": __import__("time").time(),
            "last_updated": __import__("time").time()
        })

    @classmethod
    def get_session_buffer_content(cls, session_id: str) -> str:
        """Get the buffer content as a string for sending to clients."""
        buffer_data = cls.get_session_buffer(session_id)
        lines = buffer_data.get("lines", [])
        return "".join([line.get("content", "") for line in lines])

    @classmethod
    def clear_session_buffer(cls, session_id: str):
        """Clear the persistent buffer for a session."""
        if session_id in cls.session_buffers:
            cls.session_buffers[session_id]["lines"] = []
            cls.session_buffers[session_id]["last_updated"] = __import__("time").time()

    @classmethod
    def cleanup_old_buffers(cls, max_age_hours: int = 24):
        """Clean up old buffer data for inactive sessions."""
        current_time = __import__("time").time()
        max_age_seconds = max_age_hours * 3600
        
        sessions_to_remove = []
        for session_id, buffer_data in cls.session_buffers.items():
            if (current_time - buffer_data.get("last_updated", 0)) > max_age_seconds:
                # Only remove if session is also closed
                if session_id in cls.closed_sessions or session_id not in cls.sessions:
                    sessions_to_remove.append(session_id)
        
        for session_id in sessions_to_remove:
            del cls.session_buffers[session_id]
            log.info(f"Cleaned up old buffer for session {session_id}")

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
        """Get the shell command to execute."""
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
                            
                            # Record performance metric for data reading
                            data_size = len(data)
                            self.record_performance_metric("pty_data_size", data_size, "bytes")
                            
                            self.send(text)
                        except Exception as e:
                            log.error(f"Error decoding PTY data: {e}")
                            self.record_error_event("pty_decode_error", str(e))

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
            
            # Record user interaction for local analysis
            self.record_user_interaction("terminal_input", message[:100])
            
            # Detect potential commands
            message_clean = message.strip()
            if message_clean and not message_clean.startswith('\x1b') and len(message_clean) > 2:
                # Record as potential command for analysis
                start_time = __import__("time").time()
                self.record_command_execution(message_clean, exit_code=None, execution_time=None)
            
            # Write to PTY
            await asyncio.get_event_loop().run_in_executor(
                None, os.write, self.fd, message.encode("utf-8")
            )
        except Exception as e:
            log.error(f"Error writing to PTY: {e}")
            # Record error for analysis
            self.record_error_event("pty_write_error", str(e))
            await self.close()

    async def resize(self, cols, rows):
        """Resize the PTY."""
        if self.closed or not self.fd:
            return

        try:
            start_time = __import__("time").time()
            s = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, s)
            
            # Record performance metric
            resize_time = (__import__("time").time() - start_time) * 1000  # Convert to ms
            self.record_performance_metric("terminal_resize_time", resize_time, "ms")
            
            # Record user interaction
            self.record_user_interaction("terminal_resize", f"{cols}x{rows}")
            
            log.info("SIZE (%d, %d)" % (cols, rows))
        except Exception as e:
            log.error(f"Error resizing PTY: {e}")
            self.record_error_event("pty_resize_error", str(e))

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
            from aetherterm.agentserver.infrastructure.config.di_container import get_container
            from aetherterm.agentserver.infrastructure.config.utils import render_motd

            # Get configuration from DI container
            try:
                # Try to get injected values, fallback to defaults if not available
                unsecure = getattr(get_container().application.config(), "unsecure", lambda: False)()
                i_hereby_declare = getattr(
                    get_container().application.config(),
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
            from aetherterm.agentserver.infrastructure.config.di_container import get_container
            from aetherterm.agentserver.infrastructure.config.utils import render_motd

            # Get configuration from DI container
            try:
                # Try to get injected values, fallback to defaults if not available
                unsecure = getattr(get_container().application.config(), "unsecure", lambda: False)()
                i_hereby_declare = getattr(
                    get_container().application.config(),
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

    @classmethod
    async def start_log_processing(cls):
        """Start the global log processing task."""
        if cls.log_processing_task is None:
            cls.log_processing_task = asyncio.create_task(cls._log_processing_loop())
            log.info("Log processing task started")

    @classmethod
    async def stop_log_processing(cls):
        """Stop the global log processing task."""
        if cls.log_processing_task:
            cls.log_processing_task.cancel()
            try:
                await cls.log_processing_task
            except asyncio.CancelledError:
                pass
            cls.log_processing_task = None
            log.info("Log processing task stopped")

    @classmethod
    async def _log_processing_loop(cls):
        """Main log processing loop that runs periodically."""
        log.info("Starting log processing loop")

        while True:
            try:
                await asyncio.sleep(5)  # Process logs every 5 seconds

                if cls.log_buffer:
                    # Process accumulated logs
                    logs_to_process = cls.log_buffer.copy()
                    cls.log_buffer.clear()

                    processed_batch = await cls._process_log_batch(logs_to_process)

                    if processed_batch:
                        # Add to processed logs with size limit
                        cls.processed_logs.extend(processed_batch)

                        # Keep only the last 1000 processed logs
                        if len(cls.processed_logs) > 1000:
                            cls.processed_logs = cls.processed_logs[-1000:]

                        # Broadcast to subscribers
                        await cls._broadcast_log_updates(processed_batch)

                        log.debug(f"Processed {len(processed_batch)} log entries")

            except asyncio.CancelledError:
                log.info("Log processing loop cancelled")
                break
            except Exception as e:
                log.error(f"Error in log processing loop: {e}")
                # Continue processing despite errors

    @classmethod
    async def _process_log_batch(cls, logs: List[Dict]) -> List[Dict]:
        """Process a batch of logs and categorize them."""
        processed = []

        for log_entry in logs:
            try:
                # Extract text content
                text = log_entry.get("content", "").strip()
                if not text:
                    continue

                # Categorize log entry
                category = cls._categorize_log(text)

                # Extract timestamp or use current time
                timestamp = log_entry.get("timestamp", datetime.now().isoformat())

                # Create processed log entry
                processed_entry = {
                    "id": f"{log_entry.get('session_id', 'unknown')}_{int(time.time() * 1000)}_{len(processed)}",
                    "session_id": log_entry.get("session_id", "unknown"),
                    "timestamp": timestamp,
                    "content": text,
                    "category": category,
                    "severity": cls._get_severity(category),
                    "metadata": {
                        "length": len(text),
                        "lines": text.count("\n") + 1,
                        "has_ansi": bool(re.search(r"\x1b\[[0-9;]*m", text)),
                    },
                }

                processed.append(processed_entry)

            except Exception as e:
                log.error(f"Error processing log entry: {e}")
                continue

        return processed

    @classmethod
    def _categorize_log(cls, text: str) -> str:
        """Categorize log text based on patterns."""
        text_lower = text.lower()

        # Check each category
        for category, patterns in cls.log_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return category

        # Check for command patterns
        if re.match(r"^\$|\#", text.strip()):
            return "command"

        # Check for system messages
        if any(keyword in text_lower for keyword in ["system", "kernel", "daemon"]):
            return "system"

        return "general"

    @classmethod
    def _get_severity(cls, category: str) -> int:
        """Get numeric severity for a category."""
        severity_map = {
            "error": 5,
            "warning": 4,
            "info": 3,
            "success": 2,
            "command": 1,
            "system": 3,
            "general": 1,
        }
        return severity_map.get(category, 1)

    @classmethod
    async def _broadcast_log_updates(cls, new_logs: List[Dict]):
        """Broadcast log updates to subscribed WebSocket clients."""
        if not cls.log_subscribers or not new_logs:
            return

        # Prepare broadcast message
        message = {
            "type": "log_update",
            "logs": new_logs,
            "timestamp": datetime.now().isoformat(),
            "total_count": len(cls.processed_logs),
        }

        # Broadcast to all subscribers
        disconnected_subscribers = set()

        for subscriber in cls.log_subscribers:
            try:
                if hasattr(subscriber, "send") and callable(subscriber.send):
                    await subscriber.send(json.dumps(message))
            except Exception as e:
                log.warning(f"Failed to send log update to subscriber: {e}")
                disconnected_subscribers.add(subscriber)

        # Remove disconnected subscribers
        cls.log_subscribers -= disconnected_subscribers

    def add_to_log_buffer(self, content: str):
        """Add terminal output to the global log buffer."""
        if content and content.strip():
            log_entry = {
                "session_id": self.session,
                "content": content,
                "timestamp": datetime.now().isoformat(),
                "user": self.user.name if self.user else "unknown",
                "source": "terminal",
            }

            self.log_buffer.append(log_entry)

            # Limit buffer size
            if len(self.log_buffer) > 10000:
                self.log_buffer = self.log_buffer[-5000:]  # Keep last 5000 entries

    @classmethod
    def subscribe_to_logs(cls, subscriber):
        """Subscribe a WebSocket client to log updates."""
        cls.log_subscribers.add(subscriber)
        log.info(f"New log subscriber added. Total: {len(cls.log_subscribers)}")

    @classmethod
    def unsubscribe_from_logs(cls, subscriber):
        """Unsubscribe a WebSocket client from log updates."""
        cls.log_subscribers.discard(subscriber)
        log.info(f"Log subscriber removed. Total: {len(cls.log_subscribers)}")

    @classmethod
    def get_recent_logs(cls, limit: int = 100, category: Optional[str] = None) -> List[Dict]:
        """Get recent processed logs with optional category filtering."""
        logs = cls.processed_logs

        if category:
            logs = [log for log in logs if log.get("category") == category]

        return logs[-limit:] if logs else []

    @classmethod
    def get_log_statistics(cls) -> Dict:
        """Get statistics about processed logs."""
        if not cls.processed_logs:
            return {
                "total": 0,
                "by_category": {},
                "by_severity": {},
                "sessions": [],
                "latest_timestamp": None,
            }

        # Count by category
        by_category = {}
        by_severity = {}
        sessions = set()

        for log_entry in cls.processed_logs:
            category = log_entry.get("category", "unknown")
            severity = log_entry.get("severity", 1)
            session_id = log_entry.get("session_id", "unknown")

            by_category[category] = by_category.get(category, 0) + 1
            by_severity[severity] = by_severity.get(severity, 0) + 1
            sessions.add(session_id)

        return {
            "total": len(cls.processed_logs),
            "by_category": by_category,
            "by_severity": by_severity,
            "sessions": list(sessions),
            "latest_timestamp": cls.processed_logs[-1].get("timestamp")
            if cls.processed_logs
            else None,
        }

    @classmethod
    async def initialize_short_term_memory(cls, agent_id: str):
        """短期記憶マネージャーを初期化"""
        if cls.short_term_memory_manager is None:
            cls.short_term_memory_manager = ShortTermMemoryManager(agent_id)
            await cls.short_term_memory_manager.start()
            log.info(f"Short-term memory manager initialized for agent {agent_id}")
        
        # ローカル分析器も初期化
        if cls.local_analyzer is None:
            cls.local_analyzer = LocalShortTermAnalyzer(agent_id)
            await cls.local_analyzer.start()
            log.info(f"Local short-term analyzer initialized for agent {agent_id}")

    @classmethod
    def set_control_server_connection(cls, websocket):
        """ControlServer接続を設定"""
        if cls.short_term_memory_manager:
            cls.short_term_memory_manager.set_control_server_websocket(websocket)
            log.info("ControlServer connection set for short-term memory")

    def record_command_execution(
        self, command: str, exit_code: int = None, execution_time: float = None
    ):
        """コマンド実行を短期記憶に記録"""
        if self.short_term_memory_manager:
            self.short_term_memory_manager.record_command_execution(
                session_id=self.session,
                command=command,
                exit_code=exit_code,
                execution_time=execution_time,
            )
        
        # ローカル分析器にも記録
        if self.local_analyzer:
            self.local_analyzer.record_command(
                session_id=self.session,
                command=command,
                exit_code=exit_code,
                execution_time=execution_time,
            )

    def record_user_interaction(self, interaction_type: str, details: str = None):
        """ユーザーインタラクションを短期記憶に記録"""
        if self.short_term_memory_manager:
            self.short_term_memory_manager.record_user_interaction(
                session_id=self.session, interaction_type=interaction_type, details=details
            )
        
        # ローカル分析器にも記録
        if self.local_analyzer:
            self.local_analyzer.record_user_interaction(
                session_id=self.session,
                interaction_type=interaction_type,
                details=details,
            )

    def record_error_event(self, error_type: str, error_message: str, stack_trace: str = None):
        """エラーイベントを短期記憶に記録"""
        if self.short_term_memory_manager:
            self.short_term_memory_manager.record_error_event(
                session_id=self.session,
                error_type=error_type,
                error_message=error_message,
                stack_trace=stack_trace,
            )
        
        # ローカル分析器にも記録
        if self.local_analyzer:
            self.local_analyzer.record_error(
                session_id=self.session,
                error_type=error_type,
                error_message=error_message,
            )

    def record_performance_metric(
        self, metric_name: str, value: float, unit: str = None, threshold_exceeded: bool = False
    ):
        """パフォーマンスメトリクスを短期記憶に記録"""
        if self.short_term_memory_manager:
            self.short_term_memory_manager.record_performance_metric(
                session_id=self.session,
                metric_name=metric_name,
                value=value,
                unit=unit,
                threshold_exceeded=threshold_exceeded,
            )
        
        # ローカル分析器にも記録
        if self.local_analyzer:
            self.local_analyzer.record_performance(
                session_id=self.session,
                metric_name=metric_name,
                value=value,
                unit=unit,
            )

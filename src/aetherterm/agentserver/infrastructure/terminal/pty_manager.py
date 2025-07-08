"""
PTY Manager - Infrastructure Layer

Handles low-level PTY (pseudo-terminal) operations.
This is infrastructure concern as it deals with OS-level resources.
"""

import os
import pty
import struct
import fcntl
import termios
import logging
from typing import Tuple, Optional

log = logging.getLogger(__name__)


class PTYManager:
    """Manages PTY (pseudo-terminal) operations at the infrastructure level."""

    @staticmethod
    def create_pty(rows: int = 24, cols: int = 80) -> Tuple[int, int]:
        """
        Create a new PTY with specified dimensions.

        Args:
            rows: Number of terminal rows
            cols: Number of terminal columns

        Returns:
            Tuple of (master_fd, slave_fd)
        """
        master_fd, slave_fd = pty.openpty()

        # Set terminal size
        PTYManager.set_terminal_size(master_fd, rows, cols)

        return master_fd, slave_fd

    @staticmethod
    def set_terminal_size(fd: int, rows: int, cols: int) -> None:
        """
        Set the terminal window size.

        Args:
            fd: File descriptor
            rows: Number of rows
            cols: Number of columns
        """
        try:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
        except Exception as e:
            log.error(f"Failed to set terminal size: {e}")

    @staticmethod
    def make_non_blocking(fd: int) -> None:
        """Make a file descriptor non-blocking."""
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    @staticmethod
    def spawn_shell(
        slave_fd: int,
        user_name: Optional[str] = None,
        path: Optional[str] = None,
        shell_cmd: Optional[str] = None,
    ) -> int:
        """
        Spawn a shell in the PTY.

        Args:
            slave_fd: Slave file descriptor
            user_name: User to run shell as
            path: Working directory
            shell_cmd: Shell command to execute

        Returns:
            Process ID of the spawned shell
        """
        pid = os.fork()

        if pid == 0:  # Child process
            # Make this process a session leader
            os.setsid()

            # Make the slave PTY the controlling terminal
            fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)

            # Duplicate slave to stdin/stdout/stderr
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)

            # Close the original slave FD
            os.close(slave_fd)

            # Change to requested directory
            if path:
                try:
                    os.chdir(os.path.expanduser(path))
                except Exception as e:
                    log.error(f"Failed to change directory to {path}: {e}")

            # Set up environment
            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            env["COLORTERM"] = "truecolor"

            if user_name:
                env["USER"] = user_name
                env["LOGNAME"] = user_name

            # Execute shell
            shell = shell_cmd or os.environ.get("SHELL", "/bin/bash")

            try:
                os.execve(shell, [shell], env)
            except Exception as e:
                # If shell fails, try fallback shells
                for fallback in ["/bin/bash", "/bin/sh"]:
                    try:
                        os.execve(fallback, [fallback], env)
                        break
                    except:
                        continue

                # If all shells fail, exit
                os._exit(1)

        return pid

    @staticmethod
    def cleanup_pty(master_fd: int, slave_fd: int, pid: Optional[int] = None) -> None:
        """
        Clean up PTY resources.

        Args:
            master_fd: Master file descriptor
            slave_fd: Slave file descriptor
            pid: Process ID to terminate (optional)
        """
        # Close file descriptors
        try:
            os.close(master_fd)
        except:
            pass

        try:
            os.close(slave_fd)
        except:
            pass

        # Terminate process if provided
        if pid:
            try:
                os.kill(pid, 9)
                os.waitpid(pid, 0)
            except:
                pass

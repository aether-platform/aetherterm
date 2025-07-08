"""
System utilities - imports from parent utils module for backward compatibility.
"""

from .. import utils

# Re-export functions from parent utils module
get_lsof_socket_line = getattr(utils, "get_lsof_socket_line", None)
get_procfs_socket_line = getattr(utils, "get_procfs_socket_line", None)
get_socket_env = getattr(utils, "get_socket_env", None)

# If functions don't exist in parent, provide stubs
if get_lsof_socket_line is None:

    def get_lsof_socket_line(*args, **kwargs):
        return None


if get_procfs_socket_line is None:

    def get_procfs_socket_line(*args, **kwargs):
        return None


if get_socket_env is None:

    def get_socket_env(*args, **kwargs):
        return {}

"""Main WebSocket handlers with improved organization."""

# Import handler modules
from .handlers.base import set_sio_instance
from .handlers.connection import (
    connect,
    disconnect,
    reconnect_session,
    session_cleanup,
)
from .handlers.terminal import (
    create_terminal,
    resume_terminal,
    get_session_info,
    terminal_input,
    terminal_resize,
)
from .handlers.agent import (
    agent_start_request,
    spec_upload,
    spec_query,
    agent_hello,
)
from .handlers.workspace import (
    resume_workspace,
    on_workspace_connect,
    workspace_get,
    on_workspace_create,
    on_workspace_update,
    tab_create,
    tab_close,
)
from .handlers.monitoring import (
    log_monitor_subscribe,
    log_monitor_unsubscribe,
    log_monitor_search,
    control_message,
    wrapper_session_sync,
    get_wrapper_sessions,
    start_log_monitoring_background_task,
    stop_log_monitoring_background_task,
    start_redis_pubsub_listener,
)

# Re-export all handlers for backward compatibility
__all__ = [
    "set_sio_instance",
    "connect",
    "disconnect", 
    "reconnect_session",
    "session_cleanup",
    "create_terminal",
    "resume_terminal",
    "get_session_info",
    "terminal_input",
    "terminal_resize",
    "agent_start_request",
    "spec_upload",
    "spec_query",
    "agent_hello",
    "resume_workspace",
    "on_workspace_connect",
    "workspace_get",
    "on_workspace_create",
    "on_workspace_update",
    "tab_create",
    "tab_close",
    "log_monitor_subscribe",
    "log_monitor_unsubscribe",
    "log_monitor_search",
    "control_message",
    "wrapper_session_sync",
    "get_wrapper_sessions",
    "start_log_monitoring_background_task",
    "stop_log_monitoring_background_task",
    "start_redis_pubsub_listener",
]
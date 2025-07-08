"""
Server Lifecycle & Event Registration Module - Web Interface Layer

Handles server startup, shutdown, and event registration.
Implements Clean Architecture principles with proper separation of concerns.
"""

import logging
import webbrowser
from typing import Dict, Any, Callable, Optional
import uvicorn

from aetherterm.agentserver.endpoint.websocket import socket_handlers
from aetherterm.core.container import DIContainer

log = logging.getLogger("aetherterm.interfaces.web.lifecycle_manager")


class SocketIOEventRegistrar:
    """Handles registration of Socket.IO event handlers."""
    
    def __init__(self, sio: Any):
        """Initialize with Socket.IO server instance."""
        self.sio = sio
        
    def register_all_handlers(self) -> None:
        """Register all Socket.IO event handlers."""
        self._register_core_handlers()
        self._register_ai_handlers()
        self._register_log_monitoring_handlers()
        self._register_context_inference_handlers()
        self._register_agent_communication_handlers()
        self._register_specification_handlers()
        self._register_agent_initialization_handlers()
        
        log.info("All Socket.IO event handlers registered")
        
    def _register_core_handlers(self) -> None:
        """Register core terminal handlers."""
        handlers = [
            ("connect", socket_handlers.connect),
            ("disconnect", socket_handlers.disconnect),
            ("create_terminal", socket_handlers.create_terminal),
            ("resume_workspace", socket_handlers.resume_workspace),
            ("resume_terminal", socket_handlers.resume_terminal),
            ("reconnect_session", socket_handlers.reconnect_session),
            ("terminal_input", socket_handlers.terminal_input),
            ("terminal_resize", socket_handlers.terminal_resize),
        ]
        
        for event, handler in handlers:
            self.sio.on(event, handler)
            
        log.debug("Core terminal handlers registered")
        
    def _register_ai_handlers(self) -> None:
        """Register AI-specific handlers."""
        handlers = [
            ("wrapper_session_sync", socket_handlers.wrapper_session_sync),
            ("get_wrapper_sessions", socket_handlers.get_wrapper_sessions),
            ("unblock_request", socket_handlers.unblock_request),
            ("get_block_status", socket_handlers.get_block_status),
        ]
        
        for event, handler in handlers:
            self.sio.on(event, handler)
            
        log.debug("AI-specific handlers registered")
        
    def _register_log_monitoring_handlers(self) -> None:
        """Register log monitoring handlers."""
        handlers = [
            ("log_monitor_subscribe", socket_handlers.log_monitor_subscribe),
            ("log_monitor_unsubscribe", socket_handlers.log_monitor_unsubscribe),
            ("log_monitor_search", socket_handlers.log_monitor_search),
        ]
        
        for event, handler in handlers:
            self.sio.on(event, handler)
            
        log.debug("Log monitoring handlers registered")
        
    def _register_context_inference_handlers(self) -> None:
        """Register context inference handlers."""
        handlers = [
            ("context_inference_subscribe", socket_handlers.context_inference_subscribe),
            ("predict_next_commands", socket_handlers.predict_next_commands),
            ("get_operation_analytics", socket_handlers.get_operation_analytics),
        ]
        
        for event, handler in handlers:
            self.sio.on(event, handler)
            
        log.debug("Context inference handlers registered")
        
    def _register_agent_communication_handlers(self) -> None:
        """Register agent communication handlers."""
        handlers = [
            ("agent_start_request", socket_handlers.agent_start_request),
            ("control_message", socket_handlers.control_message),
        ]
        
        for event, handler in handlers:
            self.sio.on(event, handler)
            
        log.debug("Agent communication handlers registered")
        
    def _register_specification_handlers(self) -> None:
        """Register specification input system handlers."""
        handlers = [
            ("spec_upload", socket_handlers.spec_upload),
            ("spec_query", socket_handlers.spec_query),
        ]
        
        for event, handler in handlers:
            self.sio.on(event, handler)
            
        log.debug("Specification system handlers registered")
        
    def _register_agent_initialization_handlers(self) -> None:
        """Register agent initialization handlers."""
        handlers = [
            ("agent_hello", socket_handlers.agent_hello),
        ]
        
        for event, handler in handlers:
            self.sio.on(event, handler)
            
        log.debug("Agent initialization handlers registered")


class ServerLifecycleManager:
    """Manages server lifecycle including startup and shutdown operations."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize lifecycle manager with configuration."""
        self.config = config
        self.startup_tasks = []
        self.shutdown_tasks = []
        
    def add_startup_task(self, task: Callable) -> None:
        """Add a startup task."""
        self.startup_tasks.append(task)
        
    def add_shutdown_task(self, task: Callable) -> None:
        """Add a shutdown task."""
        self.shutdown_tasks.append(task)
        
    async def execute_startup_sequence(self) -> None:
        """Execute all startup tasks in sequence."""
        log.info("Starting server startup sequence")
        
        await self._startup_inventory_service()
        await self._startup_log_processing()
        await self._startup_context_inference()
        await self._startup_log_monitoring()
        await self._startup_short_term_memory()
        await self._startup_control_server_connection()
        
        # Execute additional startup tasks
        for task in self.startup_tasks:
            try:
                await task()
                log.debug("Startup task executed: %s", task.__name__)
            except Exception as e:
                log.warning("Startup task failed: %s - %s", task.__name__, e)
                
        log.info("Server startup sequence completed")
        
    async def execute_shutdown_sequence(self) -> None:
        """Execute all shutdown tasks in sequence."""
        log.info("Starting server shutdown sequence")
        
        # Execute custom shutdown tasks
        for task in self.shutdown_tasks:
            try:
                await task()
                log.debug("Shutdown task executed: %s", task.__name__)
            except Exception as e:
                log.warning("Shutdown task failed: %s - %s", task.__name__, e)
                
        await self._shutdown_log_processing()
        
        log.info("Server shutdown sequence completed")
        
    async def _startup_inventory_service(self) -> None:
        """Initialize inventory service."""
        try:
            from aetherterm.agentserver.services.inventory_service import inventory_service
            await inventory_service.initialize()
            log.info("Inventory service initialized successfully")
        except Exception as e:
            log.warning("Failed to initialize inventory service: %s", e)
            
    async def _startup_log_processing(self) -> None:
        """Initialize log processing service."""
        try:
            from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal
            await AsyncioTerminal.start_log_processing()
            log.info("Log processing service started successfully")
        except Exception as e:
            log.warning("Failed to start log processing service: %s", e)
            
    async def _startup_context_inference(self) -> None:
        """Initialize context inference system."""
        try:
            from aetherterm.agentserver.context_inference import initialize_context_inference
            from aetherterm.logprocessing.log_processing_manager import get_log_processing_manager

            # Get storage instances from log processing manager
            manager = get_log_processing_manager()
            if manager and manager.vector_storage and manager.sql_storage:
                initialize_context_inference(manager.vector_storage, manager.sql_storage)
                log.info("Context inference system initialized successfully")
            else:
                log.warning("Cannot initialize context inference: storage not available")
        except Exception as e:
            log.warning("Failed to initialize context inference: %s", e)
            
    async def _startup_log_monitoring(self) -> None:
        """Start log monitoring background task."""
        try:
            socket_handlers.start_log_monitoring_background_task()
            log.info("Log monitoring background task started")
        except Exception as e:
            log.warning("Failed to start log monitoring: %s", e)
            
    async def _startup_short_term_memory(self) -> None:
        """Initialize short-term memory functionality."""
        try:
            from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal
            
            # Generate agent ID (host:port based)
            host = self.config.get("host", "localhost")
            port = self.config.get("port", 57575)
            agent_id = f"agentserver_{host}_{port}"
            
            await AsyncioTerminal.initialize_short_term_memory(agent_id)
            log.info("Short-term memory initialized for agent: %s", agent_id)
        except Exception as e:
            log.warning("Failed to initialize short-term memory: %s", e)
            
    async def _startup_control_server_connection(self) -> None:
        """Initialize ControlServer connection."""
        try:
            from aetherterm.agentserver.control_server_client import ControlServerClient
            
            # Generate agent ID (host:port based)
            host = self.config.get("host", "localhost")
            port = self.config.get("port", 57575)
            agent_id = f"agentserver_{host}_{port}"
            
            control_client = ControlServerClient(agent_id=agent_id)
            await control_client.start()
            log.info("ControlServer connection established for agent: %s", agent_id)
        except Exception as e:
            log.warning("Failed to connect to ControlServer: %s", e)
            
    async def _shutdown_log_processing(self) -> None:
        """Stop log processing service."""
        try:
            from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal
            await AsyncioTerminal.stop_log_processing()
            log.info("Log processing service stopped")
        except Exception as e:
            log.warning("Error stopping log processing service: %s", e)


class ServerSetupOrchestrator:
    """Orchestrates the complete server setup process."""
    
    def __init__(self):
        """Initialize the setup orchestrator."""
        self.lifecycle_manager = None
        self.event_registrar = None
        
    def setup_application(self, asgi_app: Any, sio: Any, config: Dict[str, Any]) -> Any:
        """Setup the complete application with all components."""
        # Initialize lifecycle manager
        self.lifecycle_manager = ServerLifecycleManager(config)
        
        # Initialize event registrar
        self.event_registrar = SocketIOEventRegistrar(sio)
        
        # Wire DI container
        self._wire_dependency_injection()
        
        # Set Socket.IO instance in handlers
        socket_handlers.set_sio_instance(sio)
        
        # Register all event handlers
        self.event_registrar.register_all_handlers()
        
        # Setup auto-blocker integration
        self._setup_auto_blocker(sio)
        
        # Add lifecycle event handlers to FastAPI app
        self._setup_lifecycle_events(asgi_app)
        
        log.info("AetherTerm AgentServer application setup complete")
        return asgi_app
        
    def _wire_dependency_injection(self) -> None:
        """Wire dependency injection modules."""
        try:
            DIContainer.wire_modules([socket_handlers])
            log.debug("Dependency injection modules wired")
        except Exception as e:
            log.warning("Failed to wire DI modules: %s", e)
            
    def _setup_auto_blocker(self, sio: Any) -> None:
        """Setup auto-blocker integration."""
        try:
            from aetherterm.agentserver.auto_blocker import set_socket_io_instance
            set_socket_io_instance(sio)
            log.debug("Auto-blocker integration setup complete")
        except Exception as e:
            log.warning("Failed to setup auto-blocker: %s", e)
            
    def _setup_lifecycle_events(self, asgi_app: Any) -> None:
        """Setup FastAPI lifecycle events."""
        if hasattr(asgi_app, "other_asgi_app") and asgi_app.other_asgi_app:
            fastapi_app = asgi_app.other_asgi_app
            fastapi_app.add_event_handler("startup", self.lifecycle_manager.execute_startup_sequence)
            fastapi_app.add_event_handler("shutdown", self.lifecycle_manager.execute_shutdown_sequence)
            log.debug("FastAPI lifecycle events configured")


class UvicornServerManager:
    """Manages Uvicorn server configuration and startup."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize server manager with configuration."""
        self.config = config
        
    def create_server(self, asgi_app: Any, ssl_args: Optional[Dict] = None) -> uvicorn.Server:
        """Create configured Uvicorn server."""
        host = self.config["host"]
        port = self.config["port"]
        
        # Configure logging level
        log_level = self._get_log_level()
        log_level_name = logging.getLevelName(log_level).lower()
        if log_level_name == "warning":
            log_level_name = "warn"  # uvicorn uses 'warn' instead of 'warning'
            
        # Create server configuration
        server_config = uvicorn.Config(
            app=asgi_app,
            host=host,
            port=port,
            log_level=log_level_name,
            reload=self.config.get("debug", False),  # Enable reload in debug mode
            **(ssl_args or {})
        )
        
        server = uvicorn.Server(server_config)
        log.info("Uvicorn server configured for %s:%s", host, port)
        return server
        
    def show_startup_url(self) -> None:
        """Show the server URL and optionally open browser."""
        host = self.config["host"]
        port = self.config["port"]
        unsecure = self.config["unsecure"]
        one_shot = self.config["one_shot"]
        uri_root_path = self.config["uri_root_path"]
        
        # Construct URL
        protocol = "http" if unsecure else "https"
        path_suffix = f"{uri_root_path.strip('/') + '/' if uri_root_path else ''}"
        url = f"{protocol}://{host}:{port}/{path_suffix}"
        
        if not one_shot or not webbrowser.open(url):
            log.warning("Butterfly is ready, open your browser to: %s", url)
            
    def _get_log_level(self) -> int:
        """Get logging level from configuration."""
        log_level = logging.WARNING
        if self.config["debug"]:
            log_level = logging.INFO
            if self.config["more"]:
                log_level = logging.DEBUG
        return log_level
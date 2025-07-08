"""
Dependency Injection Container - Infrastructure Layer

Simple DI container using standard library for managing service dependencies.
"""

import logging
import os
from typing import Dict, Any, Optional

from aetherterm.agentserver.infrastructure.external.ai_service import AIService
from aetherterm.agentserver.infrastructure.external.jupyterhub_auth import JupyterHubAuthService
from aetherterm.agentserver.infrastructure.external.s3_credential_service import S3CredentialService


class SimpleContainer:
    """Simple dependency injection container."""
    
    def __init__(self):
        self._instances: Dict[str, Any] = {}
        # Check environment variables for LM Studio configuration
        # Check both AETHERTERM_AI_PROVIDER and AI_PROVIDER
        ai_provider = os.getenv("AETHERTERM_AI_PROVIDER") or os.getenv("AI_PROVIDER", "mock")
        lmstudio_url = os.getenv("LMSTUDIO_URL", "http://localhost:1234")
        
        # Log the environment variables
        logging.info(f"AI_PROVIDER from env: {ai_provider}")
        logging.info(f"LMSTUDIO_URL from env: {lmstudio_url}")
        
        # Auto-detect LM Studio if it's running and provider is mock
        if ai_provider == "mock":
            import socket
            try:
                # Extract host and port from URL
                from urllib.parse import urlparse
                parsed = urlparse(lmstudio_url)
                host = parsed.hostname or 'localhost'
                port = parsed.port or 1234
                
                # Test if LM Studio is running
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.5)
                result = sock.connect_ex((host, port))
                sock.close()
                if result == 0:
                    ai_provider = "lmstudio"
                    logging.info(f"LM Studio detected on {host}:{port}, switching to lmstudio provider")
                else:
                    logging.info(f"LM Studio not detected on {host}:{port} (connection result: {result})")
            except Exception as e:
                logging.warning(f"LM Studio auto-detection failed: {e}")
        elif ai_provider == "lmstudio":
            logging.info(f"Using explicitly configured LMStudio provider at {lmstudio_url}")
        
        logging.info(f"Final AI provider: {ai_provider}")
        
        self._config: Dict[str, Any] = {
            "debug": False,
            "more": False,
            "ai": {
                "provider": ai_provider,
                "api_key": os.getenv("AI_API_KEY", ""),
                "model": os.getenv("AI_MODEL", "default"),
                "lmstudio_url": lmstudio_url
            },
            "jupyterhub": {
                "hub_api_url": "http://hub:8081/hub/api",
                "hub_api_token": None,
                "cache_duration_minutes": 30
            },
            "s3": {
                "aws_region": "us-east-1",
                "assume_role_arn": None,
                "bucket_prefix": "jupyter-user-",
                "credential_duration_hours": 12
            }
        }
    
    def get(self, service_name: str) -> Any:
        """Get service instance."""
        if service_name not in self._instances:
            self._instances[service_name] = self._create_service(service_name)
        return self._instances[service_name]
    
    def _create_service(self, service_name: str) -> Any:
        """Create service instance."""
        if service_name == "ai_service":
            return AIService(
                provider=self._config["ai"]["provider"],
                api_key=self._config["ai"]["api_key"],
                model=self._config["ai"]["model"],
                lmstudio_url=self._config["ai"]["lmstudio_url"]
            )
        elif service_name == "jupyterhub_auth":
            return JupyterHubAuthService(
                hub_api_url=self._config["jupyterhub"]["hub_api_url"],
                hub_api_token=self._config["jupyterhub"]["hub_api_token"],
                cache_duration_minutes=self._config["jupyterhub"]["cache_duration_minutes"]
            )
        elif service_name == "s3_credential_service":
            jupyterhub_auth = self.get("jupyterhub_auth")
            return S3CredentialService(
                aws_region=self._config["s3"]["aws_region"],
                assume_role_arn=self._config["s3"]["assume_role_arn"],
                bucket_prefix=self._config["s3"]["bucket_prefix"],
                credential_duration_hours=self._config["s3"]["credential_duration_hours"],
                jupyterhub_auth=jupyterhub_auth
            )
        else:
            raise ValueError(f"Unknown service: {service_name}")
    
    def set_config(self, key: str, value: Any):
        """Set configuration value."""
        keys = key.split(".")
        config = self._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value


class InfrastructureContainer:
    """Infrastructure layer services container."""
    
    def __init__(self, container: SimpleContainer):
        self._container = container
    
    def ai_service(self) -> AIService:
        """Get AI service instance."""
        return self._container.get("ai_service")
    
    def jupyterhub_auth(self) -> JupyterHubAuthService:
        """Get JupyterHub authentication service instance."""
        return self._container.get("jupyterhub_auth")
    
    def s3_credential_service(self) -> S3CredentialService:
        """Get S3 credential service instance."""
        return self._container.get("s3_credential_service")


class ApplicationContainer:
    """Application layer services container."""
    
    def __init__(self, container: SimpleContainer):
        self._container = container
    
    def config(self) -> Dict[str, Any]:
        """Get application configuration."""
        return self._container._config


class MainContainer:
    """Main application container."""
    
    def __init__(self):
        self._container = SimpleContainer()
        self.infrastructure = InfrastructureContainer(self._container)
        self.application = ApplicationContainer(self._container)
        self.config = ConfigProxy(self._container)


class ConfigProxy:
    """Configuration proxy for compatibility."""
    
    def __init__(self, container: SimpleContainer):
        self._container = container
    
    class DebugProxy:
        def __init__(self, container: SimpleContainer):
            self._container = container
        
        def from_value(self, value: bool):
            self._container.set_config("debug", value)
    
    class MoreProxy:
        def __init__(self, container: SimpleContainer):
            self._container = container
        
        def from_value(self, value: bool):
            self._container.set_config("more", value)
    
    @property
    def debug(self):
        return self.DebugProxy(self._container)
    
    @property 
    def more(self):
        return self.MoreProxy(self._container)


# Global container instance
_container_instance = None

def setup_di_container() -> MainContainer:
    """Setup and return configured DI container."""
    global _container_instance
    
    if _container_instance is None:
        _container_instance = MainContainer()
        # Basic configuration
        _container_instance.config.debug.from_value(False)
        _container_instance.config.more.from_value(False)
    
    return _container_instance

def get_container() -> MainContainer:
    """Get the current DI container instance."""
    global _container_instance
    if _container_instance is None:
        _container_instance = setup_di_container()
    return _container_instance
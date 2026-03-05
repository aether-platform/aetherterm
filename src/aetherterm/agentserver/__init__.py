#!/usr/bin/env python

"""AetherTerm Server Package

This package contains the main server components for AetherTerm,
including the FastAPI server, Socket.IO handlers, and terminal management.
"""

from .api.server import create_asgi_app
from .main import start_server

__all__ = ["create_asgi_app", "start_server"]

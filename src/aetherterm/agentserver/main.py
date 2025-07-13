#!/usr/bin/env python
"""
AetherTerm AgentServer - Main Entry Point

Clean Architecture + Dependency Injection enabled server.
"""

import sys
import os

# Import the main server function from presentation layer
from aetherterm.agentserver.presentation.web.main import main

if __name__ == "__main__":
    main()

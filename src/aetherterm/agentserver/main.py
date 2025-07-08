#!/usr/bin/env python
"""
AetherTerm AgentServer - Main Entry Point

Clean Architecture + Dependency Injection enabled server.
"""

import sys
import os

# Add the current directory to Python path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Import the main server function from interfaces layer
from interfaces.web.main import main

if __name__ == "__main__":
    main()

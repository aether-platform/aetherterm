#!/usr/bin/env python3
"""Test environment variables"""

import os

print("Environment variables:")
print(f"AI_PROVIDER: {os.getenv('AI_PROVIDER', 'NOT SET')}")
print(f"AETHERTERM_AI_PROVIDER: {os.getenv('AETHERTERM_AI_PROVIDER', 'NOT SET')}")
print(f"LMSTUDIO_URL: {os.getenv('LMSTUDIO_URL', 'NOT SET')}")

# Also test DI container
import sys

sys.path.append("src")

from aetherterm.agentserver.infrastructure.config.di_container import SimpleContainer

print("\nDI Container test:")
container = SimpleContainer()
print(f"AI Provider from container: {container._config['ai']['provider']}")
print(f"LMStudio URL from container: {container._config['ai']['lmstudio_url']}")

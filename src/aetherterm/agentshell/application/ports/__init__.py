"""
ポートインターフェース

外部依存を抽象化するインターフェースを定義します。
"""

from .ai_provider import AIProviderPort
from .server_connector import ServerConnectorPort
from .terminal_io import TerminalIOPort

__all__ = [
    "AIProviderPort",
    "ServerConnectorPort",
    "TerminalIOPort",
]

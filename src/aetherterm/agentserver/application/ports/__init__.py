"""
ポートインターフェース

外部依存（Socket.IO, NATS, DB等）を抽象化するインターフェースを定義します。
ドメイン層・アプリケーション層はこれらのインターフェースのみに依存し、
具体的な実装はアダプター層で提供されます。
"""

from .broadcaster import BroadcasterPort
from .terminal_repository import TerminalRepositoryPort
from .ai_service import AIServicePort

__all__ = [
    "BroadcasterPort",
    "TerminalRepositoryPort",
    "AIServicePort",
]

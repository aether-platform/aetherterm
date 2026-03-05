"""
ポートインターフェース

外部依存を抽象化するインターフェースを定義します。
"""

from .messaging import MessagingPort

__all__ = [
    "MessagingPort",
]

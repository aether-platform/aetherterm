"""
Helper functions for socket handlers.

Socket.IO インスタンス管理とリクエストからのユーザー情報抽出を担当します。
ビジネスロジック（所有権確認、ターミナルコンテキスト取得）は
ドメイン/アプリケーション層に移譲済みです。
"""

import logging

log = logging.getLogger("aetherterm.socket_handlers")

# Global storage for socket.io server instance
sio_instance = None


def set_sio_instance(sio):
    """Set the global socket.io server instance."""
    global sio_instance
    sio_instance = sio


def get_sio():
    """Get the global socket.io server instance."""
    return sio_instance


def get_user_info_from_environ(environ):
    """Extract user information from environment/headers."""
    return {
        "remote_addr": environ.get("REMOTE_ADDR"),
        "remote_user": environ.get("HTTP_X_REMOTE_USER"),
        "forwarded_for": environ.get("HTTP_X_FORWARDED_FOR"),
        "user_agent": environ.get("HTTP_USER_AGENT"),
    }

"""
PTY通信パッケージ

util-linux-ngのscriptコマンドと同じアーキテクチャを使用して
PTYマスター/スレーブペアでターミナル通信を管理します。

2つのPTY実装を提供:
- TerminalPTY: 非同期PTY通信（既存）
- SyncTerminalPTY: 同期PTY通信 + 非同期バックエンド（test.pyから統合）
"""

from .sync_terminal_pty import (
    AsyncWorker,
    SyncTerminalPTY,
    TerminalUtils,
    default_async_log,
    run_shell_with_async_backend,
)
from .terminal_pty import TerminalBuffer, TerminalPTY

__all__ = [
    # 非同期PTY
    "TerminalPTY",
    "TerminalBuffer",
    # 同期PTY + 非同期バックエンド
    "SyncTerminalPTY",
    "AsyncWorker",
    "TerminalUtils",
    "run_shell_with_async_backend",
    "default_async_log",
]

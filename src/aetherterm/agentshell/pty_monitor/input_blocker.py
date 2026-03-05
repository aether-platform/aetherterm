"""
Input Blocker

危険検出時のユーザー入力ブロック機能。
Ctrl+D検出による解除機能を含む。

ドメインサービス (InputPolicyService) にブロック状態のビジネスロジックを委譲し、
このクラスはターミナルI/O（stdin監視、表示）のインフラ層を担当します。
"""

import logging
import select
import sys
import termios
import threading
import tty
from enum import Enum
from typing import Callable, Optional

from ..domain.services.input_policy import BlockState as DomainBlockState
from ..domain.services.input_policy import InputPolicyService

logger = logging.getLogger(__name__)


class BlockState(Enum):
    """ブロック状態（後方互換性のため残す。ドメイン層の BlockState を参照）"""

    NORMAL = "normal"
    BLOCKED = "blocked"
    WAITING_CONFIRMATION = "waiting_confirmation"


def _to_legacy_state(domain_state: DomainBlockState) -> BlockState:
    """ドメイン状態をレガシー状態に変換"""
    return BlockState(domain_state.value)


class InputBlocker:
    """入力制御クラス

    ブロック状態のビジネスロジックは InputPolicyService に委譲し、
    ターミナルI/O（stdin監視、表示）を担当します。
    """

    def __init__(self, policy: Optional[InputPolicyService] = None):
        """初期化"""
        self._policy = policy or InputPolicyService()
        self.original_settings = None
        self.input_thread = None
        self.running = False
        self.unblock_callback: Optional[Callable[[], None]] = None
        self._lock = threading.Lock()

    @property
    def state(self) -> BlockState:
        """後方互換性のための状態プロパティ"""
        return _to_legacy_state(self._policy.state)

    @state.setter
    def state(self, value: BlockState):
        """後方互換性のための状態セッター"""
        if value == BlockState.BLOCKED:
            self._policy.block("manual")
        elif value == BlockState.NORMAL:
            self._policy.force_unblock()

    def set_unblock_callback(self, callback: Callable[[], None]):
        """
        ブロック解除時のコールバック関数を設定

        Args:
            callback: ブロック解除時に呼び出される関数
        """
        self.unblock_callback = callback

    def start_monitoring(self):
        """入力監視を開始"""
        if self.running:
            logger.warning("Input monitoring is already running")
            return

        try:
            # 元の端末設定を保存
            self.original_settings = termios.tcgetattr(sys.stdin)

            self.running = True

            # 入力監視スレッド開始
            self.input_thread = threading.Thread(target=self._input_monitor_loop)
            self.input_thread.daemon = True
            self.input_thread.start()

            logger.info("Started input monitoring")

        except Exception as e:
            logger.error(f"Failed to start input monitoring: {e}")
            raise

    def stop_monitoring(self):
        """入力監視を停止"""
        self.running = False

        # 元の端末設定を復元
        if self.original_settings:
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.original_settings)
            except Exception as e:
                logger.error(f"Failed to restore terminal settings: {e}")
            finally:
                self.original_settings = None

        if self.input_thread and self.input_thread.is_alive():
            self.input_thread.join(timeout=2)

        logger.info("Stopped input monitoring")

    def block_input(self, reason: str = "危険なコマンドが検出されました"):
        """
        入力をブロック

        Args:
            reason: ブロック理由
        """
        with self._lock:
            if not self._policy.is_blocked:
                self._policy.block(reason)
                self._display_block_message(reason)
                logger.warning(f"Input blocked: {reason}")

    def unblock_input(self):
        """入力ブロックを解除"""
        with self._lock:
            if self._policy.is_blocked:
                self._policy.force_unblock()
                self._display_unblock_message()
                logger.info("Input unblocked")

                if self.unblock_callback:
                    try:
                        self.unblock_callback()
                    except Exception as e:
                        logger.error(f"Error in unblock callback: {e}")

    def is_blocked(self) -> bool:
        """入力がブロックされているかどうかを返す"""
        return self._policy.is_blocked

    def _input_monitor_loop(self):
        """入力監視ループ（別スレッドで実行）"""
        while self.running:
            try:
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    current_state = self._policy.state
                    if current_state == DomainBlockState.BLOCKED:
                        self._handle_blocked_input()
                    elif current_state == DomainBlockState.WAITING_CONFIRMATION:
                        self._handle_confirmation_input()

            except Exception as e:
                if self.running:
                    logger.error(f"Error in input monitor loop: {e}")
                break

    def _handle_blocked_input(self):
        """ブロック中の入力処理"""
        try:
            tty.setraw(sys.stdin.fileno())
            char = sys.stdin.read(1)

            # Ctrl+D (ASCII 4) の検出
            if ord(char) == 4:
                with self._lock:
                    new_state = self._policy.handle_ctrl_d()
                    if new_state == DomainBlockState.WAITING_CONFIRMATION:
                        self._display_confirmation_message()
            else:
                self._display_block_reminder()

        except Exception as e:
            logger.error(f"Error handling blocked input: {e}")
        finally:
            if self.original_settings:
                try:
                    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.original_settings)
                except Exception:
                    pass

    def _handle_confirmation_input(self):
        """確認待ち中の入力処理"""
        try:
            tty.setraw(sys.stdin.fileno())
            char = sys.stdin.read(1)

            # Ctrl+D (ASCII 4) の再検出で解除
            if ord(char) == 4:
                self.unblock_input()
            else:
                # その他の入力でブロック状態に戻る
                with self._lock:
                    self._policy.block("確認がキャンセルされました")
                    self._display_block_message("確認がキャンセルされました")

        except Exception as e:
            logger.error(f"Error handling confirmation input: {e}")
        finally:
            if self.original_settings:
                try:
                    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.original_settings)
                except Exception:
                    pass

    def _display_block_message(self, reason: str):
        """ブロックメッセージを表示"""
        message = f"""
\033[1;31m
╔══════════════════════════════════════════════════════════════╗
║                    ⚠️  CRITICAL ALERT ⚠️                     ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  {reason:<58} ║
║                                                              ║
║  入力がブロックされました。                                    ║
║  続行するには Ctrl+D を押してください。                        ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
\033[0m
"""
        print(message, flush=True)

    def _display_confirmation_message(self):
        """確認メッセージを表示"""
        message = """
\033[1;33m
╔══════════════════════════════════════════════════════════════╗
║                      🔓 確認が必要です                        ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  本当に続行しますか？                                          ║
║                                                              ║
║  続行する場合: もう一度 Ctrl+D を押してください                 ║
║  キャンセル:   他のキーを押してください                        ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
\033[0m
"""
        print(message, flush=True)

    def _display_unblock_message(self):
        """ブロック解除メッセージを表示"""
        message = """
\033[1;32m
╔══════════════════════════════════════════════════════════════╗
║                    ✅ ブロック解除                            ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  入力ブロックが解除されました。                                ║
║  通常の操作を続行できます。                                    ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
\033[0m
"""
        print(message, flush=True)

    def _display_block_reminder(self):
        """ブロック中のリマインダーメッセージを表示"""
        message = (
            "\033[1;31m⚠️  入力がブロックされています。Ctrl+D を押して確認してください。\033[0m"
        )
        print(message, flush=True)

    def __enter__(self):
        """コンテキストマネージャー対応"""
        self.start_monitoring()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストマネージャー対応"""
        self.stop_monitoring()

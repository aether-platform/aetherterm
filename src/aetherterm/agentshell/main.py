"""Wrapperプログラムメインエントリーポイント

新しいパッケージ構成に対応したメイン実行ファイル
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

import click

from .containers import get_application, reset_application

logger = logging.getLogger(__name__)


class WrapperMain:
    """Wrapperプログラムメインクラス"""

    def __init__(self, config_path: Optional[Path] = None):
        # 環境変数から設定ファイルのパスを取得
        import os

        env_config_path = os.environ.get("AETHERTERM_CONFIG_PATH")
        if env_config_path:
            config_path = Path(env_config_path)

        logger.debug(f"設定ファイルのパス: {config_path}")
        # 設定ファイルのパスをファイルに書き込む
        try:
            with open("config_path.txt", "w") as f:
                f.write(str(config_path))
        except Exception as e:
            logger.error(f"設定ファイルのパスをファイルに書き込めませんでした: {e}")
        self.app = get_application(config_path)
        self._running = False
        self._terminal_controller = None

    async def start(self, command: Optional[list] = None) -> None:
        """Wrapperプログラムを開始"""
        try:
            # アプリケーションを初期化
            await self.app.initialize()

            # シグナルハンドラーを設定
            self._setup_signal_handlers()

            # セッションIDを生成
            from .utils import generate_session_id

            session_id = generate_session_id()

            # ターミナルコントローラーを作成
            self._terminal_controller = self.app.create_terminal_controller(session_id)

            # 監視を開始
            await self._terminal_controller.start_monitoring(command)

            self._running = True
            logger.info("Wrapperプログラムが開始されました")

            # メインループ
            await self._main_loop()

        except KeyboardInterrupt:
            logger.info("キーボード割り込みを受信しました")
        except Exception as e:
            logger.error(f"Wrapperプログラムの実行中にエラーが発生しました: {e}")
            raise
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Wrapperプログラムを停止"""
        if not self._running:
            return

        logger.info("Wrapperプログラムを停止します")
        self._running = False

        try:
            # ターミナル監視を停止
            if self._terminal_controller:
                await self._terminal_controller.stop_monitoring()

            # アプリケーションを終了
            await self.app.shutdown()

        except Exception as e:
            logger.error(f"Wrapperプログラムの停止中にエラーが発生しました: {e}")

        logger.info("Wrapperプログラムが停止されました")

    async def _main_loop(self) -> None:
        """メインループ"""
        while self._running:
            try:
                # 子プロセスが実行中かチェック
                if self._terminal_controller and not self._terminal_controller.is_child_running():
                    logger.info("子プロセスが終了しました")
                    break

                # 短時間待機
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"メインループでエラーが発生しました: {e}")
                break

    def _setup_signal_handlers(self) -> None:
        """シグナルハンドラーを設定"""

        def signal_handler(signum, frame):
            logger.info(f"シグナル {signum} を受信しました")
            self._running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)


@click.command()
@click.option(
    "--config", "-c", type=click.Path(exists=True, path_type=Path), help="設定ファイルのパス"
)
@click.option("--debug", "-d", is_flag=True, help="デバッグモードを有効にする")
@click.option("--command", help="実行するコマンド（デフォルト: シェル）")
@click.option("--agent-id", default=None, help="NATS agent ID（NATS bridge有効化）")
@click.option("--nats-url", default=None, help="NATS server URL")
@click.option("--agent-role", default="shell", help="Agent role for NATS registration")
def cli_main(config: Optional[Path], debug: bool, command: Optional[str],
             agent_id: Optional[str], nats_url: Optional[str], agent_role: str) -> None:
    """AetherTerm Wrapper - ターミナル監視とAI連携プログラム

    scriptコマンドライクなターミナル監視機能に加えて、
    AI連携とセッション管理機能を提供します。
    """
    # ログレベルを設定
    if debug:
        logging.basicConfig(
            level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    else:
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    # NATS bridge 環境変数を設定（containers.pyが参照）
    import os
    if agent_id:
        os.environ["AGENT_ID"] = agent_id
        if nats_url:
            os.environ["NATS_URL"] = nats_url
        elif "NATS_URL" not in os.environ:
            os.environ["NATS_URL"] = "nats://localhost:4222"
        os.environ["AGENT_ROLE"] = agent_role

    # コマンドを解析
    cmd_list = None
    if command:
        cmd_list = command.split()

    # メインプログラムを実行
    wrapper_main = WrapperMain(config)

    try:
        asyncio.run(wrapper_main.start(cmd_list))
    except KeyboardInterrupt:
        logger.info("プログラムが中断されました")
    except Exception as e:
        logger.error(f"プログラムの実行に失敗しました: {e}")
        sys.exit(1)
    finally:
        # アプリケーションインスタンスをリセット
        reset_application()


def main() -> None:
    """メイン関数（スクリプトエントリーポイント用）"""
    cli_main()


if __name__ == "__main__":
    main()

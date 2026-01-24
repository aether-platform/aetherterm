#!/usr/bin/env python3
"""
ControlServer - システム制御・管理サーバー

複数ターミナルの一括制御とログ解析を行うサーバー
"""

import asyncio
import logging
import signal
import sys

import click
import uvloop

from .central_controller import CentralController

# ログ設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
class ControlServerApp:
    """ControlServerアプリケーション"""

    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        self.controller = None

    async def start(self):
        """サーバー開始"""
        logger.info(f"ControlServer starting on {self.host}:{self.port}")

        # CentralControllerを初期化
        self.controller = CentralController(host=self.host, port=self.port)

        # サーバー開始
        await self.controller.start()

        # 状態監視ループ
        while True:
            await asyncio.sleep(30)  # 30秒間隔で状態をログ出力
            status = self.controller.get_status_summary()
            logger.info(
                f"Status: {status['agent_servers_count']} agents, "
                f"{status['active_sessions_count']} sessions, "
                f"{status['active_blocks_count']} active blocks"
            )

    async def stop(self):
        """サーバー停止"""
        if self.controller:
            await self.controller.stop()
        logger.info("ControlServer stopped")
async def main_async(host: str, port: int, debug: bool):
    """非同期メイン関数"""
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)

    app = ControlServerApp(host=host, port=port)

    # シグナルハンドラー設定
    def signal_handler():
        logger.info("Received shutdown signal")
        asyncio.create_task(app.stop())

    # Windowsでは SIGTERM のみ対応
    if sys.platform != "win32":
        loop = asyncio.get_event_loop()
        for sig in [signal.SIGTERM, signal.SIGINT]:
            loop.add_signal_handler(sig, signal_handler)

    try:
        await app.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        await app.stop()
@click.command()
@click.option("--host", default="localhost", help="Host to bind to")
@click.option("--port", default=8765, help="Port to bind to")
@click.option("--debug", is_flag=True, help="Enable debug mode")
def main(host: str, port: int, debug: bool):
    """ControlServer - システム制御・管理サーバー

    複数ターミナルの一括制御機能を提供します。

    使用例:
        # 基本起動
        aetherterm-control

        # デバッグモードで起動
        aetherterm-control --debug

        # カスタムポートで起動
        aetherterm-control --port 9000
    """

    # uvloopを使用してパフォーマンス向上
    uvloop.install()

    try:
        asyncio.run(main_async(host, port, debug))
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Application error: {e}")
        sys.exit(1)
if __name__ == "__main__":
    main()

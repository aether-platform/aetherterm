"""Dummy AI Server

テスト用のダミーAIサーバー
WebSocketでログ解析リクエストを受信し、簡易的な解析結果を返す
"""

import argparse
import asyncio
import json
import logging
import re
from typing import Any, Dict

import websockets

# ログ設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class DummyAIServer:
    """ダミーAIサーバークラス"""

    def __init__(self):
        """初期化"""
        self.connected_clients = set()

        # ダミーAI解析用のパターン
        self.analysis_patterns = {
            # 非常に危険
            "critical": {
                r"rm\s+-rf\s+/": "システム全体削除の危険性が検出されました",
                r"dd\s+if=/dev/zero": "ディスク破壊コマンドが検出されました",
                r"mkfs\.\w+": "ファイルシステム破壊コマンドが検出されました",
                r"chmod\s+777\s+/": "ルートディレクトリの権限変更が検出されました",
                r"nc\s+.*-e\s+/bin/sh": "リバースシェル接続の試行が検出されました",
            },
            # 危険
            "high": {
                r"sudo\s+su\s+-": "root権限昇格の試行が検出されました",
                r"passwd\s+root": "rootパスワード変更の試行が検出されました",
                r"systemctl\s+(stop|disable)": "重要なシステムサービスの停止が検出されました",
                r"iptables\s+-F": "ファイアウォール設定の削除が検出されました",
                r"wget.*\|\s*sh": "不明なスクリプトの実行が検出されました",
            },
            # 中程度
            "medium": {
                r"sudo\s+.*": "管理者権限でのコマンド実行が検出されました",
                r"ps\s+aux\s*\|\s*grep": "プロセス監視活動が検出されました",
                r"netstat\s+-.*": "ネットワーク状態の調査が検出されました",
                r"find\s+/.*-name": "システム全体でのファイル検索が検出されました",
            },
        }

    async def handle_client(self, websocket, path):
        """クライアント接続処理

        Args:
            websocket: WebSocket接続
            path: 接続パス
        """
        client_address = websocket.remote_address
        logger.info(f"New client connected: {client_address}")

        self.connected_clients.add(websocket)

        try:
            async for message in websocket:
                await self.process_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Client disconnected: {client_address}")
        except Exception as e:
            logger.error(f"Error handling client {client_address}: {e}")
        finally:
            self.connected_clients.discard(websocket)

    async def process_message(self, websocket, message: str):
        """メッセージ処理

        Args:
            websocket: WebSocket接続
            message: 受信メッセージ
        """
        try:
            request = json.loads(message)
            action = request.get("action")

            if action == "analyze":
                response = await self.analyze_log(request.get("data", {}))
            elif action == "ping":
                response = {"status": "success", "data": {"message": "pong"}}
            else:
                response = {"status": "error", "error": f"Unknown action: {action}"}

            await websocket.send(json.dumps(response))

        except json.JSONDecodeError as e:
            error_response = {"status": "error", "error": f"Invalid JSON: {e}"}
            await websocket.send(json.dumps(error_response))
        except Exception as e:
            error_response = {"status": "error", "error": f"Processing error: {e}"}
            await websocket.send(json.dumps(error_response))

    async def analyze_log(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """ログ解析処理

        Args:
            data: 解析データ

        Returns:
            解析結果
        """
        log_line = data.get("log_line", "")
        timestamp = data.get("timestamp", 0)

        logger.info(f"Analyzing log line: {log_line}")

        # パターンマッチング解析
        threat_level = "safe"
        confidence = 0.1
        detected_keywords = []
        message = "安全なログです"
        should_block = False

        # Critical レベルチェック
        for pattern, description in self.analysis_patterns["critical"].items():
            if re.search(pattern, log_line, re.IGNORECASE):
                threat_level = "critical"
                confidence = 0.95
                detected_keywords.append(f"CRITICAL: {description}")
                message = f"CRITICAL THREAT: {description}"
                should_block = True
                break

        # High レベルチェック（Criticalが検出されていない場合）
        if threat_level == "safe":
            for pattern, description in self.analysis_patterns["high"].items():
                if re.search(pattern, log_line, re.IGNORECASE):
                    threat_level = "high"
                    confidence = 0.85
                    detected_keywords.append(f"HIGH: {description}")
                    message = f"HIGH THREAT: {description}"
                    should_block = True
                    break

        # Medium レベルチェック（上位レベルが検出されていない場合）
        if threat_level == "safe":
            for pattern, description in self.analysis_patterns["medium"].items():
                if re.search(pattern, log_line, re.IGNORECASE):
                    threat_level = "medium"
                    confidence = 0.70
                    detected_keywords.append(f"MEDIUM: {description}")
                    message = f"MEDIUM THREAT: {description}"
                    should_block = False  # Mediumレベルではブロックしない
                    break

        # 解析結果を返す
        result = {
            "status": "success",
            "data": {
                "threat_level": threat_level,
                "confidence": confidence,
                "detected_keywords": detected_keywords,
                "message": message,
                "should_block": should_block,
                "analysis_timestamp": timestamp,
                "server_info": "Dummy AI Server v1.0",
            },
        }

        logger.info(f"Analysis result: {threat_level} (confidence: {confidence})")
        return result

    async def start_server(self, host: str = "localhost", port: int = 8765):
        """サーバー開始

        Args:
            host: バインドホスト
            port: バインドポート
        """
        logger.info(f"Starting Dummy AI Server on {host}:{port}")

        async with websockets.serve(self.handle_client, host, port):
            logger.info(f"Dummy AI Server is running on ws://{host}:{port}")
            logger.info("Waiting for connections...")

            # サーバーを永続的に実行
            await asyncio.Future()  # run forever

    def get_connected_clients_count(self) -> int:
        """接続中のクライアント数を返す"""
        return len(self.connected_clients)


async def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description="Dummy AI Server for PTY Monitor")
    parser.add_argument("--host", default="localhost", help="Server host (default: localhost)")
    parser.add_argument("--port", type=int, default=8765, help="Server port (default: 8765)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    server = DummyAIServer()

    try:
        await server.start_server(args.host, args.port)
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())

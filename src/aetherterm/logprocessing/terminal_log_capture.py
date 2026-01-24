"""
ターミナルログキャプチャ

複数ターミナルの出力をリアルタイムで収集し、Redis短期メモリに保存
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from ..common.interfaces import ITerminalController
from ..langchain.storage.redis_adapter import RedisStorageAdapter

logger = logging.getLogger(__name__)
class TerminalLogCapture:
    """ターミナルログキャプチャクラス"""

    def __init__(self, redis_storage: RedisStorageAdapter):
        """
        初期化

        Args:
            redis_storage: Redis短期メモリストレージ
        """
        self.redis_storage = redis_storage
        self._terminal_controllers: Dict[str, PTYController] = {}
        self._running = False
        self._logger = logger

        # Redis キー設定
        self.redis_log_key_prefix = "terminal_logs"
        self.redis_session_key_prefix = "terminal_sessions"
        self.log_ttl = 3600  # 1時間でTTL

        # Pub/Sub チャンネル設定
        self.pub_channels = {
            "input": "terminal:input:{}",
            "output": "terminal:output:{}",
            "error": "terminal:error:{}",
            "system": "system:events",
        }

    async def initialize(self) -> None:
        """キャプチャシステム初期化"""
        if not await self.redis_storage.is_connected():
            await self.redis_storage.connect()

        self._logger.info("TerminalLogCapture initialized")

    async def add_terminal(self, terminal_id: str, log_file_path: str) -> None:
        """
        新しいターミナルを監視対象に追加

        Args:
            terminal_id: ターミナルの一意識別子
            log_file_path: 監視するログファイルパス
        """
        if terminal_id in self._terminal_controllers:
            self._logger.warning(f"Terminal {terminal_id} is already being monitored")
            return

        try:
            # PTY Controller作成
            controller = PTYController(log_file_path)

            # データ受信コールバック設定
            controller.set_data_callback(
                lambda data: asyncio.create_task(self._handle_terminal_output(terminal_id, data))
            )

            self._terminal_controllers[terminal_id] = controller

            # 監視開始
            controller.start_monitoring()

            # セッション情報をRedisに保存
            await self._save_session_info(terminal_id, log_file_path)

            self._logger.info(f"Added terminal monitoring: {terminal_id}")

        except Exception as e:
            self._logger.error(f"Failed to add terminal {terminal_id}: {e}")
            raise

    async def remove_terminal(self, terminal_id: str) -> None:
        """
        ターミナルを監視対象から削除

        Args:
            terminal_id: 削除するターミナルID
        """
        if terminal_id not in self._terminal_controllers:
            self._logger.warning(f"Terminal {terminal_id} is not being monitored")
            return

        try:
            # 監視停止
            controller = self._terminal_controllers[terminal_id]
            controller.stop_monitoring()

            # コントローラー削除
            del self._terminal_controllers[terminal_id]

            # セッション情報削除
            await self._remove_session_info(terminal_id)

            self._logger.info(f"Removed terminal monitoring: {terminal_id}")

        except Exception as e:
            self._logger.error(f"Failed to remove terminal {terminal_id}: {e}")

    async def _handle_terminal_output(self, terminal_id: str, output_data: str) -> None:
        """
        ターミナル出力データを処理してRedisに保存

        Args:
            terminal_id: ターミナルID
            output_data: 出力データ
        """
        try:
            # ログエントリ作成
            log_entry = {
                "terminal_id": terminal_id,
                "timestamp": datetime.utcnow().isoformat(),
                "raw_output": output_data,
                "size": len(output_data),
                "line_count": output_data.count("\n") + 1,
            }

            # Redisキー生成
            log_key = f"{self.redis_log_key_prefix}:{terminal_id}:{int(time.time() * 1000)}"

            # Redis保存（TTL付き）
            await self.redis_storage.set_with_ttl(
                key=log_key, value=json.dumps(log_entry), ttl_seconds=self.log_ttl
            )

            # ターミナル別ログリストに追加
            list_key = f"{self.redis_log_key_prefix}:list:{terminal_id}"
            await self.redis_storage.list_push(list_key, log_key)
            await self.redis_storage.expire(list_key, self.log_ttl)

            # Pub/Sub リアルタイム配信
            await self._publish_to_channel(terminal_id, data_type, log_entry)

            # 統計情報更新
            await self._update_statistics(terminal_id, len(output_data))

            self._logger.debug(f"Saved terminal output: {terminal_id}, size: {len(output_data)}")

        except Exception as e:
            self._logger.error(f"Failed to handle terminal output for {terminal_id}: {e}")

    def _classify_terminal_data(self, data: str) -> tuple[str, dict]:
        """
        ターミナルデータを入力/出力/エラーに分類

        Returns:
            (data_type, processed_data)
        """
        lines = data.strip().split("\n")

        for line in lines:
            line = line.strip()

            # ユーザー入力検出（プロンプト付き）
            if line.startswith("$ ") or line.startswith("# ") or line.endswith("$ "):
                command = line.replace("$ ", "").replace("# ", "").replace("$ ", "")
                return "input", {
                    "command": command,
                    "command_type": self._classify_command(command),
                    "prompt_type": "user" if line.startswith("$ ") else "root",
                }

            # エラー出力検出
            if any(
                keyword in line.lower() for keyword in ["error", "failed", "exception", "traceback"]
            ):
                return "error", {
                    "error_type": self._classify_error(line),
                    "severity": self._get_error_severity(line),
                }

        # デフォルトは出力
        return "output", {"output_type": "stdout", "has_ansi": "\x1b[" in data}

    def _classify_command(self, command: str) -> str:
        """コマンド分類"""
        if command.startswith("git"):
            return "git"
        elif command.startswith(("npm", "yarn", "pnpm")):
            return "package_manager"
        elif command.startswith(("docker", "kubectl")):
            return "container"
        elif command.startswith("sudo"):
            return "system"
        return "general"

    def _classify_error(self, error_line: str) -> str:
        """エラー分類"""
        if "permission" in error_line.lower():
            return "permission"
        elif "not found" in error_line.lower():
            return "not_found"
        elif "connection" in error_line.lower():
            return "network"
        return "general"

    def _get_error_severity(self, error_line: str) -> str:
        """エラー重要度"""
        if "fatal" in error_line.lower() or "critical" in error_line.lower():
            return "critical"
        elif "error" in error_line.lower():
            return "error"
        elif "warning" in error_line.lower():
            return "warning"
        return "info"

    async def _publish_to_channel(self, terminal_id: str, data_type: str, log_entry: dict) -> bool:
        """
        Pub/Subチャンネルにリアルタイム配信

        Args:
            terminal_id: ターミナルID
            data_type: データタイプ (input/output/error)
            log_entry: ログエントリ

        Returns:
            bool: 配信成功フラグ
        """
        try:
            # チャンネル選択
            if data_type == "error":
                channel = self.pub_channels["error"].format(terminal_id)
            elif data_type == "input":
                channel = self.pub_channels["input"].format(terminal_id)
            else:
                channel = self.pub_channels["output"].format(terminal_id)

            # 配信メッセージ作成
            message = {
                "type": "terminal_log",
                "terminal_id": terminal_id,
                "data_type": data_type,
                "timestamp": log_entry["timestamp"],
                "data": log_entry,
            }

            # Redis Pub/Sub配信
            subscriber_count = await self.redis_storage.publish(channel, json.dumps(message))

            # システムイベントチャンネルにも配信（エラーの場合）
            if data_type == "error":
                system_message = {
                    "type": "error_detected",
                    "terminal_id": terminal_id,
                    "timestamp": log_entry["timestamp"],
                    "severity": log_entry["processed_data"].get("severity", "unknown"),
                }
                await self.redis_storage.publish(
                    self.pub_channels["system"], json.dumps(system_message)
                )

            self._logger.debug(
                f"Published to channel {channel}: {data_type} ({subscriber_count} subscribers)"
            )
            return True

        except Exception as e:
            self._logger.error(f"Failed to publish to channel: {e}")
            return False

    async def _save_session_info(self, terminal_id: str, log_file_path: str) -> None:
        """セッション情報をRedisに保存"""
        session_info = {
            "terminal_id": terminal_id,
            "log_file_path": log_file_path,
            "start_time": datetime.utcnow().isoformat(),
            "status": "active",
        }

        session_key = f"{self.redis_session_key_prefix}:{terminal_id}"
        await self.redis_storage.set_with_ttl(
            key=session_key, value=json.dumps(session_info), ttl_seconds=self.log_ttl
        )

    async def _remove_session_info(self, terminal_id: str) -> None:
        """セッション情報をRedisから削除"""
        session_key = f"{self.redis_session_key_prefix}:{terminal_id}"
        await self.redis_storage.delete(session_key)

        # ログリストも削除
        list_key = f"{self.redis_log_key_prefix}:list:{terminal_id}"
        await self.redis_storage.delete(list_key)

    async def _update_statistics(self, terminal_id: str, data_size: int) -> None:
        """ターミナル統計情報を更新"""
        stats_key = f"terminal_stats:{terminal_id}"

        # 現在の統計取得
        current_stats = await self.redis_storage.get(stats_key)
        if current_stats:
            stats = json.loads(current_stats)
        else:
            stats = {
                "total_bytes": 0,
                "total_entries": 0,
                "last_update": None,
            }

        # 統計更新
        stats["total_bytes"] += data_size
        stats["total_entries"] += 1
        stats["last_update"] = datetime.utcnow().isoformat()

        # Redis保存
        await self.redis_storage.set_with_ttl(
            key=stats_key, value=json.dumps(stats), ttl_seconds=self.log_ttl
        )

    async def get_recent_logs(self, terminal_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        指定ターミナルの最近のログを取得

        Args:
            terminal_id: ターミナルID
            limit: 取得する最大ログ数

        Returns:
            ログエントリのリスト
        """
        try:
            list_key = f"{self.redis_log_key_prefix}:list:{terminal_id}"

            # 最新のログキーを取得
            log_keys = await self.redis_storage.list_range(list_key, -limit, -1)

            # ログデータを取得
            logs = []
            for log_key in reversed(log_keys):  # 新しい順
                log_data = await self.redis_storage.get(log_key)
                if log_data:
                    logs.append(json.loads(log_data))

            return logs

        except Exception as e:
            self._logger.error(f"Failed to get recent logs for {terminal_id}: {e}")
            return []

    async def get_active_terminals(self) -> List[str]:
        """アクティブなターミナルIDリストを取得"""
        return list(self._terminal_controllers.keys())

    async def get_terminal_statistics(self, terminal_id: str) -> Optional[Dict[str, Any]]:
        """ターミナル統計情報を取得"""
        try:
            stats_key = f"terminal_stats:{terminal_id}"
            stats_data = await self.redis_storage.get(stats_key)

            if stats_data:
                return json.loads(stats_data)
            return None

        except Exception as e:
            self._logger.error(f"Failed to get statistics for {terminal_id}: {e}")
            return None

    async def shutdown(self) -> None:
        """キャプチャシステムシャットダウン"""
        self._logger.info("Shutting down TerminalLogCapture...")

        # すべてのターミナル監視停止
        for terminal_id in list(self._terminal_controllers.keys()):
            await self.remove_terminal(terminal_id)

        self._running = False
        self._logger.info("TerminalLogCapture shutdown complete")

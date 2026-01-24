"""
ログプロセッサー

Redis短期メモリからログを取得し、構造化データとしてSQL中期メモリに保存
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..langchain.storage.redis_adapter import RedisStorageAdapter
from ..langchain.storage.sql_adapter import SQLStorageAdapter

logger = logging.getLogger(__name__)
class LogProcessor:
    """ログ処理クラス"""

    def __init__(
        self,
        redis_storage: RedisStorageAdapter,
        sql_storage: SQLStorageAdapter,
    ):
        """
        初期化

        Args:
            redis_storage: Redis短期メモリストレージ
            sql_storage: SQL中期メモリストレージ
        """
        self.redis_storage = redis_storage
        self.sql_storage = sql_storage
        self._logger = logger
        self._running = False

        # ANSI制御文字除去用正規表現
        self.ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

        # コマンドパターン検出
        self.command_patterns = {
            "error": re.compile(r"(?i)(error|failed|failure|exception|traceback)", re.MULTILINE),
            "warning": re.compile(r"(?i)(warning|warn)", re.MULTILINE),
            "success": re.compile(r"(?i)(success|successful|completed|done)", re.MULTILINE),
            "command": re.compile(r"^\$\s+(.+)$", re.MULTILINE),
            "git": re.compile(r"^\$\s+git\s+(.+)$", re.MULTILINE),
            "install": re.compile(
                r"(?i)(install|npm\s+install|pip\s+install|apt\s+install)", re.MULTILINE
            ),
            "build": re.compile(r"(?i)(build|compile|webpack|rollup)", re.MULTILINE),
        }

    async def initialize(self) -> None:
        """プロセッサ初期化"""
        if not await self.sql_storage.is_connected():
            await self.sql_storage.connect()

        # ターミナルログテーブル作成
        await self._create_terminal_log_tables()

        self._logger.info("LogProcessor initialized")

    async def _create_terminal_log_tables(self) -> None:
        """ターミナルログ用テーブル作成"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS terminal_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            terminal_id TEXT NOT NULL,
            session_id TEXT,
            timestamp DATETIME NOT NULL,
            log_type TEXT NOT NULL,
            command TEXT,
            output_text TEXT,
            error_level TEXT,
            metadata TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_terminal_timestamp (terminal_id, timestamp),
            INDEX idx_log_type (log_type),
            INDEX idx_error_level (error_level)
        );
        """

        try:
            await self.sql_storage.execute_query(create_table_sql, {})
            self._logger.info("Terminal logs table created/verified")
        except Exception as e:
            self._logger.error(f"Failed to create terminal logs table: {e}")
            raise

    async def start_processing(self, check_interval: int = 10) -> None:
        """
        ログ処理を開始 (Pub/Sub + ポーリングハイブリッド)

        Args:
            check_interval: Redis確認間隔（秒）
        """
        if self._running:
            self._logger.warning("LogProcessor is already running")
            return

        self._running = True
        self._logger.info("Starting log processing with Pub/Sub...")

        try:
            # Pub/Subサブスクライバー開始
            subscriber_task = asyncio.create_task(self._start_pubsub_subscriber())

            # フォールバックポーリングも継続（未処理ログのため）
            polling_task = asyncio.create_task(self._fallback_polling(check_interval))

            # 両方のタスクを並行実行
            await asyncio.gather(subscriber_task, polling_task, return_exceptions=True)

        except Exception as e:
            self._logger.error(f"Log processing error: {e}")
        finally:
            self._running = False
            self._logger.info("Log processing stopped")

    async def _start_pubsub_subscriber(self) -> None:
        """
        Redis Pub/Subサブスクライバーを開始
        """
        channels = ["terminal:input:*", "terminal:output:*", "terminal:error:*", "system:events"]

        try:
            await self.redis_storage.subscribe_with_pattern(
                patterns=channels, callback=self._handle_pubsub_message
            )
        except Exception as e:
            self._logger.error(f"Pub/Sub subscriber error: {e}")

    async def _handle_pubsub_message(self, channel: str, message: str) -> None:
        """
        Pub/Subメッセージハンドラー

        Args:
            channel: チャンネル名
            message: メッセージ内容
        """
        try:
            import json

            data = json.loads(message)

            if data.get("type") == "terminal_log":
                # ターミナルログを即座に処理
                log_entry = data.get("data", {})
                structured_logs = await self._structure_log_entry(log_entry)

                for structured_log in structured_logs:
                    await self._save_structured_log(structured_log)

                self._logger.debug(f"Processed realtime log from {channel}")

            elif data.get("type") == "error_detected":
                # エラーアラート処理
                await self._handle_error_alert(data)

        except Exception as e:
            self._logger.error(f"Failed to handle pub/sub message: {e}")

    async def _fallback_polling(self, interval: int) -> None:
        """
        フォールバックポーリング（未処理ログのため）
        """
        while self._running:
            try:
                # 定期的に未処理ログをチェック
                await self._process_pending_logs()
                await asyncio.sleep(interval * 3)  # Pub/Subがメインなので間隔を長く
            except Exception as e:
                self._logger.error(f"Fallback polling error: {e}")
                await asyncio.sleep(interval)

    async def _handle_error_alert(self, error_data: dict) -> None:
        """
        エラーアラートを処理
        """
        severity = error_data.get("severity", "unknown")
        terminal_id = error_data.get("terminal_id")

        if severity in ["critical", "error"]:
            self._logger.warning(
                f"High severity error detected on terminal {terminal_id}: {severity}"
            )
            # ここでアラート通知や自動対応を追加可能

    async def stop_processing(self) -> None:
        """ログ処理停止"""
        self._running = False

    async def force_process_missed_logs(self) -> None:
        """
        システム再起動時などの未処理ログを手動処理 (緊急時のみ)
        """
        try:
            self._logger.info("Force processing any missed logs...")
            # アクティブなターミナルリストを取得
            terminal_pattern = "terminal_logs:list:*"
            terminal_keys = await self.redis_storage.scan_keys(terminal_pattern)

            processed_count = 0
            for terminal_key in terminal_keys:
                terminal_id = terminal_key.split(":")[-1]
                count = await self._process_terminal_logs(terminal_id)
                processed_count += count

            self._logger.info(f"Force processed {processed_count} missed logs")

        except Exception as e:
            self._logger.error(f"Failed to force process missed logs: {e}")

    async def _process_terminal_logs(self, terminal_id: str) -> int:
        """指定ターミナルのログを処理 (緊急時のみ)"""
        try:
            # 未処理ログキーを取得
            list_key = f"terminal_logs:list:{terminal_id}"
            log_keys = await self.redis_storage.list_range(list_key, 0, -1)

            processed_count = 0
            for log_key in log_keys:
                # ログデータ取得
                log_data = await self.redis_storage.get(log_key)
                if not log_data:
                    continue

                log_entry = json.loads(log_data)

                # 構造化データに変換
                structured_logs = await self._structure_log_entry(log_entry)

                # SQL保存
                for structured_log in structured_logs:
                    await self._save_structured_log(structured_log)
                    processed_count += 1

                # 処理済みログをRedisから削除
                await self.redis_storage.delete(log_key)
                await self.redis_storage.list_remove(list_key, log_key)

            if processed_count > 0:
                self._logger.info(
                    f"Force processed {processed_count} logs for terminal {terminal_id}"
                )

            return processed_count

        except Exception as e:
            self._logger.error(f"Failed to process logs for terminal {terminal_id}: {e}")
            return 0

    async def _structure_log_entry(self, log_entry: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        ログエントリを構造化データに変換

        Args:
            log_entry: 生ログエントリ

        Returns:
            構造化ログエントリのリスト
        """
        raw_output = log_entry.get("raw_output", "")
        terminal_id = log_entry.get("terminal_id", "")
        timestamp = log_entry.get("timestamp", "")

        # ANSI制御文字除去
        clean_output = self.ansi_escape.sub("", raw_output)

        structured_logs = []

        # 行ごとに解析
        lines = clean_output.split("\n")
        current_command = None
        output_buffer = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # コマンド検出
            command_match = self.command_patterns["command"].match(line)
            if command_match:
                # 前のコマンドの出力を保存
                if current_command and output_buffer:
                    structured_logs.append(
                        await self._create_command_log_entry(
                            terminal_id, timestamp, current_command, "\n".join(output_buffer)
                        )
                    )

                current_command = command_match.group(1)
                output_buffer = []
                continue

            # 出力行として蓄積
            output_buffer.append(line)

            # エラーレベル判定
            error_level = self._determine_error_level(line)
            if error_level in ["ERROR", "WARNING"]:
                # 重要なログは個別に保存
                structured_logs.append(
                    await self._create_output_log_entry(terminal_id, timestamp, line, error_level)
                )

        # 最後のコマンドの出力を保存
        if current_command and output_buffer:
            structured_logs.append(
                await self._create_command_log_entry(
                    terminal_id, timestamp, current_command, "\n".join(output_buffer)
                )
            )

        # コマンドが検出されない場合は一般出力として保存
        if not structured_logs and clean_output.strip():
            error_level = self._determine_error_level(clean_output)
            structured_logs.append(
                await self._create_output_log_entry(
                    terminal_id, timestamp, clean_output, error_level
                )
            )

        return structured_logs

    async def _create_command_log_entry(
        self, terminal_id: str, timestamp: str, command: str, output: str
    ) -> Dict[str, Any]:
        """コマンド実行ログエントリ作成"""
        return {
            "terminal_id": terminal_id,
            "timestamp": timestamp,
            "log_type": "COMMAND",
            "command": command,
            "output_text": output,
            "error_level": self._determine_error_level(output),
            "metadata": json.dumps(
                {
                    "command_type": self._classify_command(command),
                    "output_lines": len(output.split("\n")),
                    "output_size": len(output),
                }
            ),
        }

    async def _create_output_log_entry(
        self, terminal_id: str, timestamp: str, output: str, error_level: str
    ) -> Dict[str, Any]:
        """一般出力ログエントリ作成"""
        return {
            "terminal_id": terminal_id,
            "timestamp": timestamp,
            "log_type": "OUTPUT",
            "command": None,
            "output_text": output,
            "error_level": error_level,
            "metadata": json.dumps(
                {
                    "output_lines": len(output.split("\n")),
                    "output_size": len(output),
                }
            ),
        }

    def _determine_error_level(self, text: str) -> str:
        """テキストからエラーレベルを判定"""
        if self.command_patterns["error"].search(text):
            return "ERROR"
        elif self.command_patterns["warning"].search(text):
            return "WARNING"
        elif self.command_patterns["success"].search(text):
            return "INFO"
        else:
            return "DEBUG"

    def _classify_command(self, command: str) -> str:
        """コマンドを分類"""
        for cmd_type, pattern in self.command_patterns.items():
            if cmd_type in ["error", "warning", "success", "command"]:
                continue
            if pattern.search(command):
                return cmd_type.upper()
        return "GENERAL"

    async def _save_structured_log(self, log_entry: Dict[str, Any]) -> None:
        """構造化ログをSQL保存"""
        insert_sql = """
        INSERT INTO terminal_logs 
        (terminal_id, timestamp, log_type, command, output_text, error_level, metadata)
        VALUES (:terminal_id, :timestamp, :log_type, :command, :output_text, :error_level, :metadata)
        """

        try:
            await self.sql_storage.execute_query(insert_sql, log_entry)
        except Exception as e:
            self._logger.error(f"Failed to save structured log: {e}")

    async def get_terminal_log_summary(self, terminal_id: str, hours: int = 24) -> Dict[str, Any]:
        """ターミナルログサマリー取得"""
        summary_sql = """
        SELECT 
            log_type,
            error_level,
            COUNT(*) as count,
            MAX(timestamp) as latest_timestamp
        FROM terminal_logs 
        WHERE terminal_id = :terminal_id 
        AND timestamp > datetime('now', '-{hours} hours')
        GROUP BY log_type, error_level
        ORDER BY count DESC
        """.format(hours=hours)

        try:
            results = await self.sql_storage.fetch_all(summary_sql, {"terminal_id": terminal_id})
            return {
                "terminal_id": terminal_id,
                "period_hours": hours,
                "summary": results,
                "generated_at": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            self._logger.error(f"Failed to get log summary for {terminal_id}: {e}")
            return {}

    async def search_logs(
        self,
        query: str,
        terminal_id: Optional[str] = None,
        error_level: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """ログ検索"""
        search_sql = """
        SELECT * FROM terminal_logs 
        WHERE (output_text LIKE :query OR command LIKE :query)
        """

        params = {"query": f"%{query}%"}

        if terminal_id:
            search_sql += " AND terminal_id = :terminal_id"
            params["terminal_id"] = terminal_id

        if error_level:
            search_sql += " AND error_level = :error_level"
            params["error_level"] = error_level

        search_sql += " ORDER BY timestamp DESC LIMIT :limit"
        params["limit"] = limit

        try:
            return await self.sql_storage.fetch_all(search_sql, params)
        except Exception as e:
            self._logger.error(f"Failed to search logs: {e}")
            return []

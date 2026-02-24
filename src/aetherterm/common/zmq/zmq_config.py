"""
ZMQ設定

ZeroMQのエンドポイント、トピック体系、タイムアウト等の設定を定義します。
Circus MCP (tcp://127.0.0.1:5555) との競合を回避するため 5560〜5562 を使用。
"""

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class ZMQConfig:
    """ZMQ接続設定"""

    enabled: bool = False

    # ROUTER/DEALER: RPC・メッセージルーティング
    broker_router_endpoint: str = "tcp://127.0.0.1:5560"
    # PUB/SUB: イベントブロードキャスト
    broker_pub_endpoint: str = "tcp://127.0.0.1:5561"
    # PUSH/PULL: タスク分配
    broker_push_endpoint: str = "tcp://127.0.0.1:5562"

    # Heartbeat
    heartbeat_interval: int = 5  # 秒
    heartbeat_timeout: int = 15  # 秒（この間heartbeatが来なければ死亡判定）

    # メッセージング
    send_timeout: int = 5000  # ミリ秒
    recv_timeout: int = 5000  # ミリ秒
    high_water_mark: int = 1000  # HWM（メッセージキューの最大サイズ）


class ZMQTopics:
    """PUB/SUBトピック体系"""

    # ターミナルI/O
    TERMINAL_OUTPUT = "terminal.output"  # terminal.output.{session_id}
    TERMINAL_INPUT = "terminal.input"  # terminal.input.{session_id}

    # Agent状態
    AGENT_STATUS = "agent.status"  # agent.status.{agent_id}
    AGENT_HEARTBEAT = "agent.heartbeat"  # agent.heartbeat.{agent_id}

    # タスク
    TASK_PROGRESS = "task.progress"  # task.progress.{task_id}

    # コマンド
    COMMAND_PROPOSED = "command.proposed"  # command.proposed.{session_id}

    # システム
    SYSTEM_BROADCAST = "system.broadcast"

    @staticmethod
    def with_id(topic: str, id: str) -> str:
        """トピックにIDを付加"""
        return f"{topic}.{id}"

    @staticmethod
    def parse_topic(full_topic: str) -> tuple:
        """トピック文字列をベーストピックとIDに分解"""
        parts = full_topic.rsplit(".", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return full_topic, ""

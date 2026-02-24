"""
AgentShell ZMQオブザーバー

AsyncioTerminalのPTYチェーンに入らず、ZMQ PUB/SUBで
ターミナルI/Oを監視し、DEALER経由でコマンドを注入する
独立オブザーバーとして動作します。

自動再接続機能を持ち、ブローカーの再起動にも追従します。

AsyncioTerminalの子プロセスではなく、スタンドアロンプロセスとして起動:
    python -m aetherterm.agentshell.main_zmq --session <session_id>

環境変数:
    AETHERTERM_ZMQ_BROKER: ブローカーROUTERアドレス (tcp://127.0.0.1:5560)
    AETHERTERM_ZMQ_PUB: ブローカーPUBアドレス (tcp://127.0.0.1:5561)
    AETHERTERM_AGENT_ID: Agent ID (自動生成される場合はNone)
"""

import argparse
import asyncio
import logging
import os
import re
import signal

from .zmq_agent_connector import ZMQAgentConnector
from ..common.zmq.zmq_config import ZMQConfig, ZMQTopics
from ..common.agent_protocol import AgentMessage, MessageType
from .pty_monitor.ai_analyzer import AIAnalyzer, ThreatLevel

logger = logging.getLogger(__name__)

# Error patterns for output monitoring
_ERROR_PATTERNS = re.compile(
    r"(?:"
    r"exit\s+code\s*[:\s]\s*[1-9]\d*"
    r"|Traceback\s*\(most recent call last\)"
    r"|(?:^|\s)error\s*:"
    r"|(?:^|\s)failed\s*:"
    r"|permission\s+denied"
    r"|segmentation\s+fault"
    r"|command\s+not\s+found"
    r"|no\s+such\s+file\s+or\s+directory"
    r"|killed"
    r"|panic:"
    r")",
    re.IGNORECASE,
)

# 再接続設定
RECONNECT_DELAY_INITIAL = 1.0   # 初回待機（秒）
RECONNECT_DELAY_MAX = 30.0      # 最大待機（秒）
RECONNECT_DELAY_MULTIPLIER = 2  # バックオフ係数


class AgentShellZMQ:
    """ZMQオブザーバーモードのAgentShell

    PTYチェーンには入らず、ZMQ PUB/SUBでターミナルI/Oを
    監視し、必要に応じてCOMMAND_INJECT/COMMAND_PROPOSEで
    コマンドを送信する独立プロセス。

    切断時は指数バックオフで自動再接続を行う。
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.agent_id = os.environ.get(
            "AETHERTERM_AGENT_ID", f"agentshell_{self.session_id}"
        )

        self.zmq_config = ZMQConfig(
            enabled=True,
            broker_router_endpoint=os.environ.get(
                "AETHERTERM_ZMQ_BROKER", "tcp://127.0.0.1:5560"
            ),
            broker_pub_endpoint=os.environ.get(
                "AETHERTERM_ZMQ_PUB", "tcp://127.0.0.1:5561"
            ),
            broker_push_endpoint=os.environ.get(
                "AETHERTERM_ZMQ_PUSH", "tcp://127.0.0.1:5562"
            ),
        )

        self.connector: ZMQAgentConnector | None = None
        self.analyzer = AIAnalyzer()
        self._running = False

    def _create_connector(self) -> ZMQAgentConnector:
        """新しいコネクターインスタンスを生成"""
        return ZMQAgentConnector(
            agent_id=self.agent_id,
            zmq_config=self.zmq_config,
            capabilities=["io_observer", "command_inject", "command_propose"],
        )

    async def run(self) -> None:
        """AgentShellオブザーバーを実行（自動再接続付き）"""
        logger.info(
            f"AgentShell ZMQ Observer starting "
            f"(session={self.session_id}, agent={self.agent_id})"
        )

        self._running = True
        reconnect_delay = RECONNECT_DELAY_INITIAL

        while self._running:
            try:
                # 新しいコネクターで接続
                self.connector = self._create_connector()
                connected = await self.connector.start()

                if not connected:
                    logger.warning(
                        f"Connection failed, retrying in {reconnect_delay:.0f}s..."
                    )
                    await self._safe_sleep(reconnect_delay)
                    reconnect_delay = min(
                        reconnect_delay * RECONNECT_DELAY_MULTIPLIER,
                        RECONNECT_DELAY_MAX,
                    )
                    continue

                # 接続成功 → バックオフをリセット
                reconnect_delay = RECONNECT_DELAY_INITIAL
                logger.info("Connected, subscribing to terminal I/O")

                # AI解析サーバーへの接続（オプション、失敗しても続行）
                ai_connected = await self.analyzer.connect_to_ai_server()
                if ai_connected:
                    logger.info("AI analyzer connected to AI server")
                else:
                    logger.info(
                        "AI analyzer running in local-only mode "
                        "(keyword-based analysis)"
                    )

                # ターミナルI/Oトピックを購読
                await self._subscribe_topics()

                logger.info(f"Observing terminal session {self.session_id}")

                # メインループ: 接続が維持される限り待機
                while self._running and self.connector.is_connected():
                    await asyncio.sleep(1.0)

                if not self._running:
                    break

                # ここに来た = 切断された
                logger.warning("Connection lost, cleaning up for reconnect...")
                await self._cleanup_connector()

                logger.info(f"Reconnecting in {reconnect_delay:.0f}s...")
                await self._safe_sleep(reconnect_delay)
                reconnect_delay = min(
                    reconnect_delay * RECONNECT_DELAY_MULTIPLIER,
                    RECONNECT_DELAY_MAX,
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected error: {e}", exc_info=True)
                await self._cleanup_connector()

                if not self._running:
                    break

                logger.info(f"Reconnecting in {reconnect_delay:.0f}s...")
                await self._safe_sleep(reconnect_delay)
                reconnect_delay = min(
                    reconnect_delay * RECONNECT_DELAY_MULTIPLIER,
                    RECONNECT_DELAY_MAX,
                )

        # 終了処理
        await self._cleanup_connector()
        logger.info("AgentShell ZMQ Observer stopped")

    async def stop(self) -> None:
        """オブザーバーを停止"""
        self._running = False

    async def _subscribe_topics(self) -> None:
        """ターミナルI/Oトピックを購読"""
        output_topic = ZMQTopics.with_id(
            ZMQTopics.TERMINAL_OUTPUT, self.session_id
        )
        input_topic = ZMQTopics.with_id(
            ZMQTopics.TERMINAL_INPUT, self.session_id
        )

        await self.connector.subscribe_topic(
            output_topic, self._on_terminal_output
        )
        await self.connector.subscribe_topic(
            input_topic, self._on_terminal_input
        )

    async def _cleanup_connector(self) -> None:
        """コネクターとAI解析サーバーを安全にクリーンアップ"""
        if self.connector:
            try:
                await self.connector.stop()
            except Exception as e:
                logger.debug(f"Connector cleanup error (ignored): {e}")
            self.connector = None

        try:
            await self.analyzer.disconnect_from_ai_server()
        except Exception as e:
            logger.debug(f"AI analyzer cleanup error (ignored): {e}")

    async def _safe_sleep(self, seconds: float) -> None:
        """_runningフラグを確認しながらスリープ（早期中断対応）"""
        elapsed = 0.0
        while elapsed < seconds and self._running:
            await asyncio.sleep(min(0.5, seconds - elapsed))
            elapsed += 0.5

    async def _on_terminal_output(
        self, topic: str, message: AgentMessage
    ) -> None:
        """ターミナル出力を受信（監視用）

        AI分析によるセキュリティ脅威検出とエラーパターン検出を行う。
        CRITICAL/HIGHレベルの脅威が検出された場合はユーザーに警告する。
        """
        data = message.payload.get("data", "")
        if not data:
            return

        logger.debug(
            f"[OUT] {data[:200]}" + ("..." if len(data) > 200 else "")
        )

        try:
            # AI解析による脅威検出
            result = await self.analyzer.analyze_log_line(data)

            if result.threat_level in (ThreatLevel.CRITICAL, ThreatLevel.HIGH):
                logger.warning(
                    f"[THREAT:{result.threat_level.value.upper()}] "
                    f"{result.message} "
                    f"(confidence={result.confidence:.2f}, "
                    f"keywords={result.detected_keywords})"
                )

                # ブロック推奨時はユーザーに警告メッセージを送信
                if result.should_block and self.connector and self.connector.is_connected():
                    warn_msg = AgentMessage(
                        from_agent=self.agent_id,
                        to_agent="broker",
                        message_type=MessageType.COMMAND_PROPOSE,
                        payload={
                            "session_id": self.session_id,
                            "warning": True,
                            "threat_level": result.threat_level.value,
                            "message": result.message,
                            "confidence": result.confidence,
                            "detected_keywords": result.detected_keywords,
                            "description": (
                                f"Security threat detected in terminal output: "
                                f"{result.message}"
                            ),
                        },
                    )
                    await self.connector.send_message(warn_msg)

            elif result.threat_level == ThreatLevel.MEDIUM:
                logger.info(
                    f"[THREAT:MEDIUM] {result.message} "
                    f"(confidence={result.confidence:.2f})"
                )

            # エラーパターン検出
            if _ERROR_PATTERNS.search(data):
                logger.info(
                    f"[ERROR_DETECTED] Error pattern found in output: "
                    f"{data[:300]}"
                )

        except Exception as e:
            logger.debug(f"Output analysis error (non-fatal): {e}")

    async def _on_terminal_input(
        self, topic: str, message: AgentMessage
    ) -> None:
        """ターミナル入力を受信（監視用）

        入力コマンドに対してAI解析を行い、危険コマンドを検出する。
        HIGH/CRITICALレベルの脅威が検出された場合はINTERVENTION_REQUESTを
        送信してユーザーに介入を求める。
        """
        data = message.payload.get("data", "")
        if not data:
            return

        logger.debug(f"[IN] {repr(data[:100])}")

        try:
            # 入力コマンドのAI解析
            result = await self.analyzer.analyze_log_line(data)

            # 監査ログ: すべてのMEDIUM以上の脅威を記録
            if result.threat_level not in (ThreatLevel.SAFE, ThreatLevel.LOW):
                logger.info(
                    f"[INPUT_ANALYSIS:{result.threat_level.value.upper()}] "
                    f"command={repr(data[:200])} "
                    f"message={result.message} "
                    f"confidence={result.confidence:.2f} "
                    f"should_block={result.should_block} "
                    f"keywords={result.detected_keywords}"
                )

            # ブロック推奨（CRITICAL/HIGH）の場合は介入リクエスト送信
            if result.should_block and self.connector and self.connector.is_connected():
                logger.warning(
                    f"[DANGEROUS_COMMAND] Requesting intervention for: "
                    f"{repr(data[:200])} - {result.message}"
                )
                intervention_msg = AgentMessage(
                    from_agent=self.agent_id,
                    to_agent="broker",
                    message_type=MessageType.INTERVENTION_REQUEST,
                    payload={
                        "session_id": self.session_id,
                        "command": data,
                        "threat_level": result.threat_level.value,
                        "message": result.message,
                        "confidence": result.confidence,
                        "detected_keywords": result.detected_keywords,
                        "action": "block",
                        "description": (
                            f"Dangerous command detected "
                            f"({result.threat_level.value.upper()}): "
                            f"{result.message}"
                        ),
                    },
                )
                await self.connector.send_message(intervention_msg)

        except Exception as e:
            logger.debug(f"Input analysis error (non-fatal): {e}")

    async def inject_command(
        self, command: str, require_approval: bool = False
    ) -> None:
        """コマンドをターミナルに注入

        Args:
            command: 実行するコマンド
            require_approval: Trueの場合、COMMAND_PROPOSEで承認を求める
        """
        if not self.connector or not self.connector.is_connected():
            logger.warning("Not connected, cannot inject command")
            return

        if require_approval:
            msg = AgentMessage(
                from_agent=self.agent_id,
                to_agent="broker",
                message_type=MessageType.COMMAND_PROPOSE,
                payload={
                    "session_id": self.session_id,
                    "command": command,
                    "description": f"Command proposed by {self.agent_id}",
                    "require_approval": True,
                },
            )
            await self.connector.send_message(msg)
            logger.info(f"Command proposed for approval: {command}")
        else:
            msg = AgentMessage(
                from_agent=self.agent_id,
                to_agent="broker",
                message_type=MessageType.COMMAND_INJECT,
                payload={
                    "session_id": self.session_id,
                    "command": command,
                },
            )
            await self.connector.send_message(msg)
            logger.info(f"Command injected: {command}")


def main() -> None:
    """エントリポイント"""
    parser = argparse.ArgumentParser(
        description="AgentShell ZMQ Observer - Monitor terminal I/O via ZMQ"
    )
    parser.add_argument(
        "--session",
        required=True,
        help="Terminal session ID to observe",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    agent_shell = AgentShellZMQ(session_id=args.session)

    # Graceful shutdown on SIGTERM/SIGINT
    loop = asyncio.new_event_loop()

    def _signal_handler():
        logger.info("Shutdown signal received")
        loop.create_task(agent_shell.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    try:
        loop.run_until_complete(agent_shell.run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()

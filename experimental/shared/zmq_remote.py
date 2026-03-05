"""ZMQ Remote Input/Output - asyncioベースのZMQリモート制御

ZMQ ROUTER/DEALER パターンで別サーバからPTYへの入力を制御。
PUB/SUB でPTY出力とイベントをリモートへ配信。

プロトコル:
  Control (ROUTER/DEALER):
    クライアント → サーバ:
      ["input", <data>]         PTYへの入力データ
      ["resize", <rows>, <cols>] ターミナルサイズ変更
      ["mode", <mode_name>]      InputMode変更 (normal/blocked/remote)
      ["block"]                  Hub側で入力ブロック (= mode blocked)
      ["unblock"]                Hub側で入力アンブロック (= mode normal)
      ["ping"]                   生存確認

    サーバ → クライアント:
      ["pong"]                   ping応答
      ["ack", <command>]         コマンド受理確認
      ["error", <message>]       エラー
      ["mode_changed", <mode>]   モード変更通知
      ["blocked"]                ブロック状態に変更された
      ["unblocked"]              ブロック解除された

  Output (PUB/SUB):
    サーバ → クライアント:
      ["output", <data>]         PTY出力データ
      ["exit", <code>]           子プロセス終了
      ["event", <json>]          状態変更イベント (block/unblock等)
"""

import asyncio
import logging
from typing import Optional

import zmq
import zmq.asyncio

from async_pty import InputMode

logger = logging.getLogger(__name__)

# デフォルトポート
DEFAULT_CONTROL_PORT = 15555  # ROUTER/DEALER
DEFAULT_OUTPUT_PORT = 15556  # PUB/SUB


class ZMQRemoteServer:
    """ZMQリモートサーバ (PTY側に組み込む)

    - ROUTER socket: リモートからのコマンド受信
    - PUB socket: PTY出力をリモートに配信
    """

    def __init__(
        self,
        control_port: int = DEFAULT_CONTROL_PORT,
        output_port: int = DEFAULT_OUTPUT_PORT,
        bind_addr: str = "tcp://*",
    ):
        self._control_port = control_port
        self._output_port = output_port
        self._bind_addr = bind_addr

        self._ctx: Optional[zmq.asyncio.Context] = None
        self._router: Optional[zmq.asyncio.Socket] = None
        self._pub: Optional[zmq.asyncio.Socket] = None
        self._recv_task: Optional[asyncio.Task] = None
        self._running = False

        # コールバック
        self._on_input: Optional[callable] = None  # async (bytes) -> None
        self._on_resize: Optional[callable] = None  # async (int, int) -> None
        self._on_mode_change: Optional[callable] = None  # async (InputMode) -> None
        self._on_block: Optional[callable] = None  # async () -> None
        self._on_unblock: Optional[callable] = None  # async () -> None

    def set_on_input(self, callback) -> None:
        """リモート入力コールバック"""
        self._on_input = callback

    def set_on_resize(self, callback) -> None:
        """リモートリサイズコールバック"""
        self._on_resize = callback

    def set_on_mode_change(self, callback) -> None:
        """リモートモード変更コールバック"""
        self._on_mode_change = callback

    def set_on_block(self, callback) -> None:
        """入力ブロックコールバック"""
        self._on_block = callback

    def set_on_unblock(self, callback) -> None:
        """入力アンブロックコールバック"""
        self._on_unblock = callback

    async def start(self) -> None:
        """ZMQサーバ起動"""
        if self._running:
            return

        self._ctx = zmq.asyncio.Context()

        # ROUTER: コマンド受信
        self._router = self._ctx.socket(zmq.ROUTER)
        self._router.bind(f"{self._bind_addr}:{self._control_port}")

        # PUB: 出力配信
        self._pub = self._ctx.socket(zmq.PUB)
        self._pub.bind(f"{self._bind_addr}:{self._output_port}")

        self._running = True
        self._recv_task = asyncio.create_task(self._recv_loop())

        logger.info(
            f"ZMQ server started: control={self._control_port}, "
            f"output={self._output_port}"
        )

    async def stop(self) -> None:
        """ZMQサーバ停止"""
        if not self._running:
            return
        self._running = False

        if self._recv_task:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass

        for sock in [self._router, self._pub]:
            if sock:
                sock.close()

        if self._ctx:
            self._ctx.term()

        logger.info("ZMQ server stopped")

    async def publish_output(self, data: bytes) -> None:
        """PTY出力をPUBで配信"""
        if self._pub and self._running:
            await self._pub.send_multipart([b"output", data])

    async def publish_exit(self, code: int) -> None:
        """子プロセス終了をPUBで配信"""
        if self._pub and self._running:
            await self._pub.send_multipart([b"exit", str(code).encode()])

    async def publish_event(self, event_type: str, detail: str = "") -> None:
        """状態変更イベントをPUBで配信"""
        if self._pub and self._running:
            import json
            payload = json.dumps({"type": event_type, "detail": detail})
            await self._pub.send_multipart([b"event", payload.encode()])

    async def _recv_loop(self) -> None:
        """ROUTERからのコマンド受信ループ"""
        try:
            while self._running:
                try:
                    frames = await asyncio.wait_for(
                        self._router.recv_multipart(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                if len(frames) < 2:
                    continue

                # ROUTER: [identity, empty, command, ...]
                identity = frames[0]
                # framesの形式に応じて処理
                # DEALERから来ると [identity, command, ...]
                cmd_frames = frames[1:]

                await self._handle_command(identity, cmd_frames)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"ZMQ recv loop error: {e}")

    async def _handle_command(
        self, identity: bytes, frames: list[bytes]
    ) -> None:
        """受信コマンドを処理"""
        if not frames:
            return

        cmd = frames[0].decode("utf-8", errors="replace")

        try:
            if cmd == "input" and len(frames) >= 2:
                data = frames[1]
                if self._on_input:
                    await self._on_input(data)
                await self._send_reply(identity, [b"ack", b"input"])

            elif cmd == "resize" and len(frames) >= 3:
                rows = int(frames[1])
                cols = int(frames[2])
                if self._on_resize:
                    await self._on_resize(rows, cols)
                await self._send_reply(identity, [b"ack", b"resize"])

            elif cmd == "mode" and len(frames) >= 2:
                mode_name = frames[1].decode()
                mode_map = {
                    "normal": InputMode.NORMAL,
                    "blocked": InputMode.BLOCKED,
                    "remote": InputMode.REMOTE,
                }
                mode = mode_map.get(mode_name)
                if mode and self._on_mode_change:
                    await self._on_mode_change(mode)
                    await self._send_reply(
                        identity, [b"mode_changed", mode_name.encode()]
                    )
                else:
                    await self._send_reply(
                        identity, [b"error", f"unknown mode: {mode_name}".encode()]
                    )

            elif cmd == "block":
                if self._on_block:
                    await self._on_block()
                await self._send_reply(identity, [b"blocked"])
                await self.publish_event("blocked")

            elif cmd == "unblock":
                if self._on_unblock:
                    await self._on_unblock()
                await self._send_reply(identity, [b"unblocked"])
                await self.publish_event("unblocked")

            elif cmd == "ping":
                await self._send_reply(identity, [b"pong"])

            else:
                await self._send_reply(
                    identity, [b"error", f"unknown command: {cmd}".encode()]
                )

        except Exception as e:
            logger.error(f"Command handling error: {e}")
            await self._send_reply(identity, [b"error", str(e).encode()])

    async def _send_reply(self, identity: bytes, frames: list[bytes]) -> None:
        """ROUTERでクライアントに返信"""
        if self._router and self._running:
            await self._router.send_multipart([identity] + frames)


class ZMQRemoteClient:
    """ZMQリモートクライアント (コントローラ側)

    - DEALER socket: コマンド送信
    - SUB socket: PTY出力受信
    """

    def __init__(
        self,
        server_addr: str = "tcp://localhost",
        control_port: int = DEFAULT_CONTROL_PORT,
        output_port: int = DEFAULT_OUTPUT_PORT,
    ):
        self._server_addr = server_addr
        self._control_port = control_port
        self._output_port = output_port

        self._ctx: Optional[zmq.asyncio.Context] = None
        self._dealer: Optional[zmq.asyncio.Socket] = None
        self._sub: Optional[zmq.asyncio.Socket] = None
        self._output_task: Optional[asyncio.Task] = None
        self._running = False

        # コールバック
        self._on_output: Optional[callable] = None  # (bytes) -> None
        self._on_exit: Optional[callable] = None  # (int) -> None
        self._on_event: Optional[callable] = None  # (dict) -> None

    def set_on_output(self, callback) -> None:
        """PTY出力受信コールバック"""
        self._on_output = callback

    def set_on_exit(self, callback) -> None:
        """子プロセス終了コールバック"""
        self._on_exit = callback

    def set_on_event(self, callback) -> None:
        """状態変更イベントコールバック"""
        self._on_event = callback

    async def connect(self) -> None:
        """ZMQサーバに接続"""
        if self._running:
            return

        self._ctx = zmq.asyncio.Context()

        # DEALER: コマンド送信
        self._dealer = self._ctx.socket(zmq.DEALER)
        self._dealer.connect(f"{self._server_addr}:{self._control_port}")

        # SUB: 出力受信 (全トピック)
        self._sub = self._ctx.socket(zmq.SUB)
        self._sub.connect(f"{self._server_addr}:{self._output_port}")
        self._sub.subscribe(b"")  # 全トピック

        self._running = True
        self._output_task = asyncio.create_task(self._output_recv_loop())

        logger.info(f"Connected to ZMQ server at {self._server_addr}")

    async def disconnect(self) -> None:
        """切断"""
        if not self._running:
            return
        self._running = False

        if self._output_task:
            self._output_task.cancel()
            try:
                await self._output_task
            except asyncio.CancelledError:
                pass

        for sock in [self._dealer, self._sub]:
            if sock:
                sock.close()

        if self._ctx:
            self._ctx.term()

        logger.info("Disconnected from ZMQ server")

    async def send_input(self, data: bytes) -> Optional[list[bytes]]:
        """PTYに入力を送信"""
        return await self._send_command([b"input", data])

    async def send_resize(self, rows: int, cols: int) -> Optional[list[bytes]]:
        """ターミナルサイズ変更"""
        return await self._send_command(
            [b"resize", str(rows).encode(), str(cols).encode()]
        )

    async def set_mode(self, mode: str) -> Optional[list[bytes]]:
        """InputMode変更 (normal/blocked/remote)"""
        return await self._send_command([b"mode", mode.encode()])

    async def block(self) -> Optional[list[bytes]]:
        """Hub側で入力ブロック"""
        return await self._send_command([b"block"])

    async def unblock(self) -> Optional[list[bytes]]:
        """Hub側で入力アンブロック"""
        return await self._send_command([b"unblock"])

    async def ping(self) -> bool:
        """生存確認"""
        reply = await self._send_command([b"ping"])
        return reply is not None and len(reply) > 0 and reply[0] == b"pong"

    async def _send_command(
        self, frames: list[bytes], timeout: float = 5.0
    ) -> Optional[list[bytes]]:
        """コマンドを送信して応答を待つ"""
        if not self._dealer or not self._running:
            return None
        try:
            await self._dealer.send_multipart(frames)
            reply = await asyncio.wait_for(
                self._dealer.recv_multipart(), timeout=timeout
            )
            return reply
        except asyncio.TimeoutError:
            logger.warning("Command timeout")
            return None
        except Exception as e:
            logger.error(f"Send error: {e}")
            return None

    async def _output_recv_loop(self) -> None:
        """SUBからの出力受信ループ"""
        try:
            while self._running:
                try:
                    frames = await asyncio.wait_for(
                        self._sub.recv_multipart(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                if len(frames) < 2:
                    continue

                topic = frames[0]
                data = frames[1]

                if topic == b"output" and self._on_output:
                    self._on_output(data)
                elif topic == b"exit" and self._on_exit:
                    code = int(data.decode())
                    self._on_exit(code)
                elif topic == b"event" and self._on_event:
                    import json
                    event = json.loads(data.decode())
                    self._on_event(event)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Output recv loop error: {e}")

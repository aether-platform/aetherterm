#!/usr/bin/env python3
"""
ControlServer - Central control and analysis server.

Subscribes to AgentServer events via NATS and performs
real-time command log analysis and security threat detection.
"""

import asyncio
import logging
import signal
import sys

import click
import uvloop

from .central_controller import CentralController

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ControlServerApp:
    """ControlServer application."""

    def __init__(self, nats_url: str = "nats://localhost:4222"):
        self.nats_url = nats_url
        self.controller = None

    async def start(self):
        """Start server."""
        logger.info(f"ControlServer starting with NATS: {self.nats_url}")

        self.controller = CentralController(nats_url=self.nats_url)
        await self.controller.start()

        # Status monitoring loop
        while True:
            await asyncio.sleep(30)
            status = self.controller.get_status_summary()
            threat_stats = status["threat_stats"]
            logger.info(
                f"Status: {status['agent_servers_count']} agents, "
                f"{status['active_sessions_count']} sessions, "
                f"{status['active_blocks_count']} active blocks, "
                f"threats: {threat_stats['total_threats_detected']}"
            )

    async def stop(self):
        """Stop server."""
        if self.controller:
            await self.controller.stop()
        logger.info("ControlServer stopped")


async def main_async(nats_url: str, debug: bool):
    """Async main function."""
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)

    app = ControlServerApp(nats_url=nats_url)

    def signal_handler():
        logger.info("Received shutdown signal")
        asyncio.create_task(app.stop())

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
@click.option("--nats-url", default="nats://localhost:4222", help="NATS server URL")
@click.option("--debug", is_flag=True, help="Enable debug mode")
def main(nats_url: str, debug: bool):
    """ControlServer - Central control and analysis server.

    Subscribes to AgentServer events via NATS and performs
    real-time command log analysis and security threat detection.

    Usage:
        # Basic startup
        aetherterm-controlserver

        # Debug mode
        aetherterm-controlserver --debug

        # Custom NATS URL
        aetherterm-controlserver --nats-url nats://nats-server:4222
    """
    uvloop.install()

    try:
        asyncio.run(main_async(nats_url, debug))
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Application error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

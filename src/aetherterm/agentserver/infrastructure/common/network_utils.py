"""
Network Utilities - Infrastructure Layer

Common network operations and utilities for socket connections, HTTP clients, etc.
"""

import socket
import ssl
import logging
import asyncio
import aiohttp
from typing import Optional, Dict, Any, Tuple, List
from urllib.parse import urlparse
from datetime import datetime, timedelta

log = logging.getLogger("aetherterm.infrastructure.network_utils")


class NetworkUtilities:
    """Centralized network operations and utilities."""

    @staticmethod
    def check_port_available(host: str = "localhost", port: int = 8080) -> bool:
        """Check if a port is available for binding."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                result = sock.connect_ex((host, port))
                return result != 0  # Port is available if connection fails
        except Exception as e:
            log.error(f"Failed to check port availability {host}:{port}: {e}")
            return False

    @staticmethod
    def find_free_port(
        start_port: int = 8000, end_port: int = 9000, host: str = "localhost"
    ) -> Optional[int]:
        """Find the first available port in range."""
        for port in range(start_port, end_port + 1):
            if NetworkUtilities.check_port_available(host, port):
                return port
        return None

    @staticmethod
    def get_local_ip() -> Optional[str]:
        """Get the local IP address."""
        try:
            # Connect to a remote address to determine local IP
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                return sock.getsockname()[0]
        except Exception as e:
            log.error(f"Failed to get local IP: {e}")
            return None

    @staticmethod
    def get_hostname() -> Optional[str]:
        """Get the system hostname."""
        try:
            return socket.gethostname()
        except Exception as e:
            log.error(f"Failed to get hostname: {e}")
            return None

    @staticmethod
    def validate_url(url: str) -> bool:
        """Validate if URL is properly formatted."""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    @staticmethod
    async def check_url_accessible(
        url: str, timeout: int = 10, expected_status: List[int] = None
    ) -> bool:
        """Check if URL is accessible."""
        try:
            expected_status = expected_status or [200, 201, 202, 204]
            timeout_obj = aiohttp.ClientTimeout(total=timeout)

            async with aiohttp.ClientSession(timeout=timeout_obj) as session:
                async with session.get(url) as response:
                    return response.status in expected_status

        except Exception as e:
            log.error(f"Failed to check URL accessibility {url}: {e}")
            return False

    @staticmethod
    async def download_file(
        url: str, destination: str, chunk_size: int = 8192, progress_callback=None
    ) -> bool:
        """Download file from URL with progress tracking."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        log.error(f"Failed to download {url}: HTTP {response.status}")
                        return False

                    total_size = int(response.headers.get("content-length", 0))
                    downloaded_size = 0

                    with open(destination, "wb") as file:
                        async for chunk in response.content.iter_chunked(chunk_size):
                            file.write(chunk)
                            downloaded_size += len(chunk)

                            if progress_callback and total_size > 0:
                                progress = (downloaded_size / total_size) * 100
                                progress_callback(progress, downloaded_size, total_size)

                    log.info(f"Successfully downloaded {url} to {destination}")
                    return True

        except Exception as e:
            log.error(f"Failed to download file from {url}: {e}")
            return False

    @staticmethod
    def create_ssl_context(
        cert_file: Optional[str] = None,
        key_file: Optional[str] = None,
        ca_file: Optional[str] = None,
        verify_mode: ssl.VerifyMode = ssl.CERT_NONE,
    ) -> ssl.SSLContext:
        """Create SSL context for secure connections."""
        try:
            context = ssl.create_default_context()
            context.verify_mode = verify_mode

            if cert_file and key_file:
                context.load_cert_chain(cert_file, key_file)

            if ca_file:
                context.load_verify_locations(ca_file)

            return context

        except Exception as e:
            log.error(f"Failed to create SSL context: {e}")
            raise

    @staticmethod
    def get_network_interface_info() -> List[Dict[str, Any]]:
        """Get information about network interfaces."""
        try:
            interfaces = []
            hostname = socket.gethostname()

            # Get all IP addresses for the hostname
            addr_info = socket.getaddrinfo(hostname, None)

            for family, type_, proto, canonname, sockaddr in addr_info:
                if family == socket.AF_INET:  # IPv4
                    interfaces.append(
                        {"family": "IPv4", "address": sockaddr[0], "hostname": hostname}
                    )
                elif family == socket.AF_INET6:  # IPv6
                    interfaces.append(
                        {"family": "IPv6", "address": sockaddr[0], "hostname": hostname}
                    )

            return interfaces

        except Exception as e:
            log.error(f"Failed to get network interface info: {e}")
            return []

    @staticmethod
    async def wait_for_port(
        host: str, port: int, timeout: int = 30, check_interval: float = 0.5
    ) -> bool:
        """Wait for a port to become available."""
        start_time = datetime.now()
        timeout_delta = timedelta(seconds=timeout)

        while datetime.now() - start_time < timeout_delta:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port), timeout=1.0
                )
                writer.close()
                await writer.wait_closed()
                return True
            except (ConnectionRefusedError, asyncio.TimeoutError, OSError):
                await asyncio.sleep(check_interval)

        return False

    @staticmethod
    def get_socket_info(sock: socket.socket) -> Dict[str, Any]:
        """Get detailed information about a socket."""
        try:
            return {
                "family": sock.family.name,
                "type": sock.type.name,
                "local_address": sock.getsockname(),
                "peer_address": sock.getpeername() if sock.getpeername() else None,
                "timeout": sock.gettimeout(),
                "blocking": sock.getblocking(),
            }
        except Exception as e:
            log.error(f"Failed to get socket info: {e}")
            return {}

    @staticmethod
    async def test_connection_speed(
        host: str, port: int, data_size: int = 1024, iterations: int = 10
    ) -> Dict[str, float]:
        """Test connection speed to a host."""
        try:
            times = []

            for _ in range(iterations):
                start_time = datetime.now()

                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(host, port), timeout=5.0
                    )

                    # Send test data
                    test_data = b"x" * data_size
                    writer.write(test_data)
                    await writer.drain()

                    # Read response (if any)
                    try:
                        await asyncio.wait_for(reader.read(1024), timeout=1.0)
                    except asyncio.TimeoutError:
                        pass

                    writer.close()
                    await writer.wait_closed()

                    elapsed = (datetime.now() - start_time).total_seconds()
                    times.append(elapsed)

                except Exception:
                    continue

                await asyncio.sleep(0.1)  # Small delay between tests

            if not times:
                return {"error": "No successful connections"}

            return {
                "min_time": min(times),
                "max_time": max(times),
                "avg_time": sum(times) / len(times),
                "successful_connections": len(times),
                "total_attempts": iterations,
            }

        except Exception as e:
            log.error(f"Failed to test connection speed to {host}:{port}: {e}")
            return {"error": str(e)}

import asyncio
import ipaddress
import logging
import struct
from contextlib import suppress

logger = logging.getLogger(__name__)


class Socks5RelayError(ConnectionError):
    pass


class Socks5TcpRelay:
    def __init__(
        self,
        proxy_host: str,
        proxy_port: int,
        target_host: str,
        target_port: int,
        *,
        connect_timeout_seconds: float = 5.0,
    ) -> None:
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.target_host = target_host
        self.target_port = target_port
        self.connect_timeout_seconds = connect_timeout_seconds
        self._server: asyncio.AbstractServer | None = None

    @property
    def local_host(self) -> str:
        return "127.0.0.1"

    @property
    def local_port(self) -> int:
        if self._server is None or not self._server.sockets:
            raise RuntimeError("SOCKS5 relay has not been started")
        return int(self._server.sockets[0].getsockname()[1])

    async def start(self) -> None:
        if self._server is not None:
            return
        self._server = await asyncio.start_server(
            self._handle_client,
            self.local_host,
            0,
        )

    async def close(self) -> None:
        server = self._server
        self._server = None
        if server is None:
            return
        server.close()
        await server.wait_closed()

    def _target_address(self) -> tuple[int, bytes]:
        try:
            address = ipaddress.ip_address(self.target_host)
        except ValueError:
            encoded = self.target_host.encode("idna")
            if not encoded or len(encoded) > 255:
                raise Socks5RelayError("Invalid SOCKS5 target hostname")
            return 0x03, bytes([len(encoded)]) + encoded

        if address.version == 4:
            return 0x01, address.packed
        return 0x04, address.packed

    async def _consume_bound_address(
        self,
        reader: asyncio.StreamReader,
        address_type: int,
    ) -> None:
        if address_type == 0x01:
            await reader.readexactly(4)
        elif address_type == 0x04:
            await reader.readexactly(16)
        elif address_type == 0x03:
            length = (await reader.readexactly(1))[0]
            await reader.readexactly(length)
        else:
            raise Socks5RelayError("Invalid SOCKS5 response address type")
        await reader.readexactly(2)

    async def _open_upstream(
        self,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        writer: asyncio.StreamWriter | None = None
        try:
            async with asyncio.timeout(self.connect_timeout_seconds):
                reader, writer = await asyncio.open_connection(
                    self.proxy_host,
                    self.proxy_port,
                )

                writer.write(b"\x05\x01\x00")
                await writer.drain()
                if await reader.readexactly(2) != b"\x05\x00":
                    raise Socks5RelayError(
                        "SOCKS5 proxy does not allow unauthenticated connections"
                    )

                address_type, address = self._target_address()
                writer.write(
                    b"\x05\x01\x00"
                    + bytes([address_type])
                    + address
                    + struct.pack("!H", self.target_port)
                )
                await writer.drain()

                response = await reader.readexactly(4)
                if response[0] != 0x05:
                    raise Socks5RelayError("Invalid SOCKS5 proxy response")
                if response[1] != 0x00:
                    raise Socks5RelayError(
                        f"SOCKS5 CONNECT failed with status {response[1]}"
                    )
                await self._consume_bound_address(reader, response[3])
                return reader, writer
        except Exception:
            if writer is not None:
                writer.close()
                with suppress(Exception):
                    await writer.wait_closed()
            raise

    @staticmethod
    async def _pump(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        while chunk := await reader.read(65536):
            writer.write(chunk)
            await writer.drain()

    async def _handle_client(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        upstream_writer: asyncio.StreamWriter | None = None
        tasks: set[asyncio.Task[None]] = set()
        try:
            upstream_reader, upstream_writer = await self._open_upstream()
            tasks = {
                asyncio.create_task(self._pump(client_reader, upstream_writer)),
                asyncio.create_task(self._pump(upstream_reader, client_writer)),
            }
            done, pending = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                task.result()
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        except (
            OSError,
            TimeoutError,
            asyncio.IncompleteReadError,
            Socks5RelayError,
        ) as exc:
            logger.warning(
                "SOCKS5 relay connection failed",
                extra={
                    "event": "analytics_socks_relay_failed",
                    "error_type": type(exc).__name__,
                },
            )
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            client_writer.close()
            with suppress(Exception):
                await client_writer.wait_closed()
            if upstream_writer is not None:
                upstream_writer.close()
                with suppress(Exception):
                    await upstream_writer.wait_closed()

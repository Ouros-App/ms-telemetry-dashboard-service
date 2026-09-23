import asyncio
import socket
import struct

import pytest

from app.clients.socks5 import Socks5TcpRelay


@pytest.mark.asyncio
async def test_relay_performs_socks5_connect_and_proxies_bytes() -> None:
    loop = asyncio.get_running_loop()
    request_details: asyncio.Future[tuple[bytes, str, int]] = loop.create_future()

    async def handle_proxy(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            greeting = await reader.readexactly(3)
            writer.write(b"\x05\x00")
            await writer.drain()

            header = await reader.readexactly(4)
            assert header == b"\x05\x01\x00\x01"
            target = socket.inet_ntoa(await reader.readexactly(4))
            port = struct.unpack("!H", await reader.readexactly(2))[0]
            request_details.set_result((greeting, target, port))

            writer.write(
                b"\x05\x00\x00\x01"
                + socket.inet_aton("127.0.0.1")
                + struct.pack("!H", 0)
            )
            await writer.drain()

            payload = await reader.readexactly(4)
            writer.write(payload[::-1])
            await writer.drain()
        except Exception as exc:
            if not request_details.done():
                request_details.set_exception(exc)
            raise
        finally:
            writer.close()
            await writer.wait_closed()

    proxy_server = await asyncio.start_server(handle_proxy, "127.0.0.1", 0)
    assert proxy_server.sockets
    proxy_port = int(proxy_server.sockets[0].getsockname()[1])

    relay = Socks5TcpRelay(
        "127.0.0.1",
        proxy_port,
        "192.168.15.11",
        55432,
        connect_timeout_seconds=1,
    )
    await relay.start()

    client_writer: asyncio.StreamWriter | None = None
    try:
        client_reader, client_writer = await asyncio.open_connection(
            relay.local_host,
            relay.local_port,
        )
        client_writer.write(b"ping")
        await client_writer.drain()

        assert await client_reader.readexactly(4) == b"gnip"
        assert await asyncio.wait_for(request_details, timeout=1) == (
            b"\x05\x01\x00",
            "192.168.15.11",
            55432,
        )
    finally:
        if client_writer is not None:
            client_writer.close()
            await client_writer.wait_closed()
        await relay.close()
        proxy_server.close()
        await proxy_server.wait_closed()

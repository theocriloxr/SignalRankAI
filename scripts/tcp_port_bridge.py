#!/usr/bin/env python3
"""Small TCP port bridge for Railway custom-domain target-port compatibility.

This process never runs SignalRank application code. It only forwards bytes from
one local TCP port to the already-running frontdoor port, so enabling an
additional Railway target port cannot duplicate schedulers, webhooks, or workers.
"""
from __future__ import annotations

import argparse
import asyncio
import signal


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        try:
            writer.write_eof()
        except (AttributeError, OSError, RuntimeError):
            pass


async def _handle_client(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    *,
    target_host: str,
    target_port: int,
) -> None:
    try:
        upstream_reader, upstream_writer = await asyncio.open_connection(target_host, target_port)
    except OSError:
        client_writer.close()
        await client_writer.wait_closed()
        return

    left = asyncio.create_task(_pipe(client_reader, upstream_writer))
    right = asyncio.create_task(_pipe(upstream_reader, client_writer))
    await asyncio.wait({left, right}, return_when=asyncio.FIRST_COMPLETED)
    for task in (left, right):
        if not task.done():
            task.cancel()
    await asyncio.gather(left, right, return_exceptions=True)
    upstream_writer.close()
    client_writer.close()
    await asyncio.gather(
        upstream_writer.wait_closed(),
        client_writer.wait_closed(),
        return_exceptions=True,
    )


async def _run(*, listen_host: str, listen_port: int, target_host: str, target_port: int) -> None:
    server = await asyncio.start_server(
        lambda r, w: _handle_client(
            r,
            w,
            target_host=target_host,
            target_port=target_port,
        ),
        host=listen_host,
        port=listen_port,
    )
    print(
        f"[port_bridge] listening {listen_host}:{listen_port} -> "
        f"{target_host}:{target_port}",
        flush=True,
    )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    async with server:
        await stop.wait()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--target-host", default="127.0.0.1")
    parser.add_argument("--target-port", type=int, required=True)
    args = parser.parse_args()
    if args.listen_port == args.target_port and args.listen_host in {"127.0.0.1", "0.0.0.0"}:
        raise SystemExit("listen and target ports must differ")
    asyncio.run(
        _run(
            listen_host=args.listen_host,
            listen_port=args.listen_port,
            target_host=args.target_host,
            target_port=args.target_port,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

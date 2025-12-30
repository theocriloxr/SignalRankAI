import asyncio
import websockets
import json

BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"

async def subscribe_ticker(symbol):
    url = f"{BINANCE_WS_URL}/{symbol.lower()}@ticker"
    async with websockets.connect(url) as ws:
        while True:
            msg = await ws.recv()
            data = json.loads(msg)
            yield data

# Example usage:
# async def main():
#     async for tick in subscribe_ticker('btcusdt'):
#         print(tick)
#
# asyncio.run(main())

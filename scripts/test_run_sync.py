from utils.async_runner import run_sync
import asyncio

async def t():
    return 1

if __name__ == '__main__':
    print('run_sync result:', run_sync(t()))

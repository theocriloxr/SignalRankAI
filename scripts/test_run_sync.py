__test__ = False

import asyncio

async def t():
    return 1

if __name__ == '__main__':
    from pathlib import Path
    import sys
    ROOT = Path(__file__).resolve().parents[1]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from utils.async_runner import run_sync
    print('run_sync result:', run_sync(t()))

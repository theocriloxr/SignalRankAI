import asyncio


def test_proxy_manager_round_robin_async(monkeypatch):
    from utils import proxy_manager

    monkeypatch.setenv("PROXY_LIST", "http://proxy1:8080,http://proxy2:8080")
    proxy_manager._INDEX = 0

    async def _run():
        a = await proxy_manager.next_proxy_url()
        b = await proxy_manager.next_proxy_url()
        c = await proxy_manager.next_proxy_url()
        return a, b, c

    p1, p2, p3 = asyncio.run(_run())
    assert p1 == "http://proxy1:8080"
    assert p2 == "http://proxy2:8080"
    assert p3 == "http://proxy1:8080"


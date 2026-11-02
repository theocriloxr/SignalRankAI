"""Economic calendar merges the next-week feed (2 Nov 2026)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from services import economic_calendar as ec


class _Resp:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http")

    def json(self):
        return self._payload


def test_next_week_events_are_merged_without_duplicates(monkeypatch):
    now = datetime.now(timezone.utc)
    this_week = [{"title": "CPI", "country": "USD", "impact": "High", "date": (now + timedelta(hours=5)).isoformat()}]
    next_week = this_week + [{"title": "NFP", "country": "USD", "impact": "High",
                              "date": (now + timedelta(days=3)).isoformat()}]

    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **k):
            return _Resp(next_week if "nextweek" in url else this_week)

    monkeypatch.setattr(ec.httpx, "AsyncClient", Client)
    events = asyncio.run(ec._fetch_forex_factory(now - timedelta(days=1), now + timedelta(days=8)))
    assert sorted(e["title"] for e in events) == ["CPI", "NFP"]

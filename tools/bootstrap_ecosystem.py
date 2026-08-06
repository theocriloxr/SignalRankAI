"""One-owner ecosystem bootstrap CLI.

Run after ``alembic upgrade head``. Network discovery is opt-in because some
providers have tight credits and Railway deploys must remain deterministic.
"""
from __future__ import annotations

import argparse
import asyncio
import json

from db.ecosystem_bootstrap import persist_instrument_registry, record_discovery_run, seed_all
from db.session import DBPriority, get_session
from data.connectors.coingecko_adapter import discover_instruments as coingecko_discover
from data.connectors.defillama_adapter import discover_instruments as defillama_discover
from data.instrument_discovery import DynamicInstrumentRegistry, run_discovery


async def _run(with_discovery: bool, top: int) -> dict:
    output: dict = {}
    async with get_session(priority=DBPriority.CRITICAL, label="ecosystem.bootstrap", timeout_seconds=30) as session:
        output["seed"] = await seed_all(session)
        if with_discovery:
            registry = DynamicInstrumentRegistry()
            providers = {"coingecko": coingecko_discover, "defillama": defillama_discover}
            rows = {}
            results = {}
            # Keep row payloads so DB mappings preserve provider metadata.
            for provider, fn in providers.items():
                try:
                    payload = list(fn(top=top) or [])
                    rows[provider] = payload
                    result = registry.ingest(provider, payload)
                    results[provider] = result.to_dict()
                except Exception as exc:
                    results[provider] = {"provider": provider, "state": "failed", "reason": str(exc)[:200]}
            output["discovery"] = results
            output["registry"] = await persist_instrument_registry(session, registry, provider_rows=rows)
            for provider, result in results.items():
                await record_discovery_run(session, provider, result)
        await session.commit()
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--discover", action="store_true", help="query enabled public discovery providers")
    parser.add_argument("--top", type=int, default=100)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(_run(args.discover, max(1, min(args.top, 500)))), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

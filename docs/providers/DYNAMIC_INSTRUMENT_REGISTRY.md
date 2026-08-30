# SignalRankAI — Dynamic Instrument Discovery & Registry

Implementation: `data/instrument_discovery.py` (+ `data/provider_activation.py`).

## Purpose

The engine universe is **provider-driven** instead of hardcoded symbol arrays.
Hardcoded lists remain only as emergency fallback, owner-pinned instruments,
test fixtures, bootstrap symbols and allow/block lists — never as the
authoritative universe.

## Data flow

```text
scheduled discovery starts
→ per enabled provider: adapter discover_instruments()
→ provider isolation (one failure never stops the others)
→ normalize rows -> CanonicalInstrument (identity = asset class + kind + base/quote)
→ ingest into DynamicInstrumentRegistry (idempotent, created/updated/unchanged)
→ provider_symbol -> canonical -> {provider: symbol} maps maintained
→ engine selects dynamic universe() with gating
```

## Canonical identity (no naive symbol merging)

`XAUTUSDT` (tokenized gold, crypto spot) and `XAUUSD` (commodity spot) are
**separate instruments** — the canonical key includes asset class:

```text
crypto:spot:XAUT:USDT:USDT:-:-:-
commodity:spot:XAU:USD:USD:-:-:-
```

They may share an underlying exposure group in portfolio risk, but they are
never merged as one tradable instrument.

## Universe selection

```python
registry.universe(
    asset_classes={"crypto", "commodity"},
    tradable_only=True,
    min_providers=1,
)
```

Gating: active status, tradability, minimum independent providers, and
asset-class ordering by scan priority. Bounded, deterministic ordering.

## Discovery orchestration

```python
from data.instrument_discovery import run_discovery

results = run_discovery(
    {"coingecko": coingecko_discover_instruments, "defillama": defillama_discover_instruments},
    min_interval_seconds=900.0,
)
```

- Per-provider cooldown (rate-limit aware).
- Provider raising/timeouting → `DiscoveryRunResult(state="failed")` only for
  that provider.
- Idempotent ingestion; re-running updates in place.

## Metrics

```text
instruments_discovered  instruments_created   symbol_mapping_failures
provider_discovery_failures (per-provider state)   dynamic_universe_size
```

## New / delisted instruments

- New instruments enter the registry immediately but are **not** delivered
  until certified (metadata → history → live quote → shadow → paper → delivery).
- Delisted instruments are marked `suspended`/`delisted`; historical records
  are never deleted; open-position monitoring continues.

"""Idempotent v1.5.1 ecosystem catalogue and instrument bootstrap.

This module deliberately performs no work at import time. Railway should run
``python -m tools.bootstrap_ecosystem`` from a single migration/bootstrap owner
only after Alembic is at head.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Iterable, Mapping

from sqlalchemy import BigInteger, String, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.asset_registry import canonicalize_asset
from core.tier_policy import TIER_ORDER, Tier, get_entitlements
from data.instrument_discovery import DynamicInstrumentRegistry
from ml.schema_version import FEATURE_SCHEMA_VERSION as ML_FEATURE_SCHEMA_VERSION, get_feature_columns

CATALOGUE_VERSION = "unified-platform-v1.5.1"
FEATURE_SCHEMA_VERSION = ML_FEATURE_SCHEMA_VERSION
LABEL_SCHEMA_VERSION = "label-schema-v1"
DATASET_VERSION = "dataset-v1-point-in-time"


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, str(default)) or default))
    except (TypeError, ValueError):
        return default


async def seed_subscription_catalogue(session: AsyncSession) -> dict[str, int]:
    """Seed the product/price/entitlement catalogue with bounded DB round-trips."""
    products = [
        ("premium_monthly", "PREMIUM", "Premium Monthly", 30, _env_int("PREMIUM_MONTHLY_PRICE_NGN", 24000)),
        ("premium_quarterly", "PREMIUM", "Premium Quarterly", 90, _env_int("PREMIUM_QUARTERLY_PRICE_NGN", 56000)),
        ("premium_yearly", "PREMIUM", "Premium Yearly", 365, _env_int("PREMIUM_YEARLY_PRICE_NGN", 192000)),
        ("vip_monthly", "VIP", "VIP Monthly", 30, _env_int("VIP_MONTHLY_PRICE_NGN", 40000)),
        ("professional_monthly", "PROFESSIONAL", "Professional", 30, _env_int("PROFESSIONAL_MONTHLY_PRICE_NGN", 0)),
        (
            "institutional_contract",
            "INSTITUTIONAL",
            "Institutional",
            365,
            _env_int("INSTITUTIONAL_CONTRACT_PRICE_NGN", 0),
        ),
    ]

    product_params = [
        {
            "product_id": product_id,
            "tier": tier,
            "display_name": name,
            "duration_days": days,
        }
        for product_id, tier, name, days, _price_ngn in products
    ]
    if product_params:
        await session.execute(
            text("""
                INSERT INTO subscription_products(product_id,tier,display_name,duration_days,active)
                VALUES (:product_id,:tier,:display_name,:duration_days,TRUE)
                ON CONFLICT (product_id) DO UPDATE SET
                  tier=EXCLUDED.tier, display_name=EXCLUDED.display_name,
                  duration_days=EXCLUDED.duration_days, active=TRUE
            """),
            product_params,
        )

    # Contract/contact-sales prices remain zero and are not public checkout products.
    # Keep one active release price per product. Explicit SQLAlchemy bind types
    # avoid asyncpg/PostgreSQL parameter ambiguity while executemany keeps the
    # bootstrap phase bounded instead of holding one DB session over hundreds of
    # sequential network round-trips.
    price_params = [
        {"product_id": product_id, "price_kobo": max(0, price_ngn) * 100}
        for product_id, _tier, _name, _days, price_ngn in products
    ]
    close_previous_price = text("""
        UPDATE subscription_prices
        SET effective_until=NOW()
        WHERE product_id=:product_id
          AND currency='NGN'
          AND effective_until IS NULL
          AND effective_from<>TIMESTAMP '2026-08-06 00:00:00'
    """).bindparams(bindparam("product_id", type_=String(64)))
    upsert_release_price = text("""
        INSERT INTO subscription_prices(product_id,currency,price_kobo,effective_from,effective_until)
        VALUES (:product_id,'NGN',:price_kobo,TIMESTAMP '2026-08-06 00:00:00',NULL)
        ON CONFLICT (product_id,currency,effective_from) DO UPDATE SET
          price_kobo=EXCLUDED.price_kobo,
          effective_until=NULL
    """).bindparams(
        bindparam("product_id", type_=String(64)),
        bindparam("price_kobo", type_=BigInteger()),
    )
    if price_params:
        await session.execute(close_previous_price, price_params)
        await session.execute(upsert_release_price, price_params)

    entitlement_params: list[dict[str, Any]] = []
    for tier in TIER_ORDER:
        if tier in {Tier.ADMIN, Tier.OWNER}:
            continue
        policy = get_entitlements(tier)
        base = {
            "signal.receive": (True, float(policy.daily_signal_limit), "day", 10),
            "signal.priority": (True, None, None, 10 + TIER_ORDER.index(tier)),
            "signal.delay_seconds": (True, float(policy.delivery_delay_minutes * 60), None, 10),
            "signal.asset_classes": (True, None, None, 10),
            "signal.timeframes": (True, None, None, 10),
            "paper.enabled": (policy.has("paper_trading") or tier is Tier.FREE, None, None, 10),
            "analytics.basic": (True, None, None, 10),
            "notifications.telegram": (True, None, None, 10),
            "notifications.web": (True, None, None, 10),
            "api.rest": (policy.has("rest_api"), None, None, 30),
            "api.websocket": (policy.has("websocket_api"), None, None, 30),
            "api.webhooks": (policy.has("outbound_webhooks") or policy.has("webhook_api"), None, None, 30),
            "research.strategy_builder": (policy.has("strategy_lab"), None, None, 30),
            "research.backtest": (policy.has("batch_backtesting"), None, None, 30),
            "organization.enabled": (policy.has("organization_tenancy"), None, None, 40),
            "white_label.enabled": (policy.has("white_label"), None, None, 40),
        }
        for feature_name in sorted(policy.features):
            base[f"feature.{feature_name}"] = (True, None, None, 20)

        configuration = {
            "policy_version": CATALOGUE_VERSION,
            "features": sorted(policy.features),
            "asset_classes": list(policy.allowed_asset_classes),
            "profiles": list(policy.allowed_profiles),
            "max_tp_levels": policy.max_tp_levels,
            "history_days": policy.history_days,
            "analytics_level": policy.analytics_level,
            "support_level": policy.support_level,
        }
        configuration_json = _json(configuration)
        for key, (enabled, limit_value, period, priority) in base.items():
            entitlement_params.append(
                {
                    "key": key,
                    "tier": tier.value,
                    "enabled": enabled,
                    "limit_value": limit_value,
                    "period": period,
                    "priority": priority,
                    "configuration": configuration_json,
                }
            )

    if entitlement_params:
        entitlement_upsert = text("""
            INSERT INTO subscription_entitlements(
              entitlement_key,tier,enabled,limit_value,period,priority,
              configuration,effective_from,version
            ) VALUES (
              :key,:tier,:enabled,:limit_value,:period,:priority,
              CAST(:configuration AS JSONB),TIMESTAMP '2026-08-06 00:00:00',1
            )
            ON CONFLICT (entitlement_key,tier,version) DO UPDATE SET
              enabled=EXCLUDED.enabled, limit_value=EXCLUDED.limit_value,
              period=EXCLUDED.period, priority=EXCLUDED.priority,
              configuration=EXCLUDED.configuration
        """)
        await session.execute(entitlement_upsert, entitlement_params)

    feature_entitlements = sum(
        len(get_entitlements(tier).features) for tier in TIER_ORDER if tier not in {Tier.ADMIN, Tier.OWNER}
    )
    entitlement_rows = len(entitlement_params)
    return {
        "products": len(products),
        "prices": len(products),
        "entitlements": entitlement_rows,
        "feature_entitlements": feature_entitlements,
        "control_entitlements": entitlement_rows - feature_entitlements,
    }


async def seed_ml_governance(session: AsyncSession) -> dict[str, int]:
    features = get_feature_columns()
    for order, name in enumerate(features):
        missing_policy = (
            "reject"
            if name
            in {
                "score_normalized",
                "risk_reward_ratio",
                "price_range",
                "risk_amount",
                "direction_enc",
                "regime_enc",
                "strategy_enc",
                "asset_class_enc",
            }
            else "explicit_missing_indicator"
        )
        await session.execute(
            text("""
            INSERT INTO feature_definitions(
              feature_name,feature_version,data_type,feature_order,
              normalization,missing_policy,provider
            ) VALUES (:name,'3','float',:feature_order,'declared',:missing_policy,'multi-source')
            ON CONFLICT (feature_name,feature_version) DO UPDATE SET
              feature_order=EXCLUDED.feature_order,
              missing_policy=EXCLUDED.missing_policy,
              provider=EXCLUDED.provider
        """),
            {"name": name, "feature_order": order, "missing_policy": missing_policy},
        )
    label_spec = {
        "version": LABEL_SCHEMA_VERSION,
        "tasks": [
            "direction",
            "tp1",
            "tp2",
            "tp3",
            "stop",
            "entry_fill",
            "expected_r",
            "mfe",
            "mae",
            "duration",
            "abstention",
        ],
        "terminal_labels": [
            "not_entered",
            "entry_filled",
            "tp1",
            "tp2",
            "tp3",
            "stop_loss",
            "break_even",
            "partial_win",
            "expired",
            "invalidated",
            "quote_unavailable",
        ],
    }
    await session.execute(
        text("""
        INSERT INTO label_versions(label_version,label_spec)
        VALUES (:version,CAST(:spec AS JSONB))
        ON CONFLICT (label_version) DO UPDATE SET label_spec=EXCLUDED.label_spec
    """),
        {"version": LABEL_SCHEMA_VERSION, "spec": _json(label_spec)},
    )
    schema_hash = hashlib.sha256("\n".join(features).encode()).hexdigest()
    await session.execute(
        text("""
        INSERT INTO dataset_versions(dataset_version,feature_schema_version,label_version,row_count,hash)
        VALUES (:dataset,:feature,:label,0,:hash)
        ON CONFLICT (dataset_version) DO UPDATE SET
          feature_schema_version=EXCLUDED.feature_schema_version,
          label_version=EXCLUDED.label_version, hash=EXCLUDED.hash
    """),
        {
            "dataset": DATASET_VERSION,
            "feature": FEATURE_SCHEMA_VERSION,
            "label": LABEL_SCHEMA_VERSION,
            "hash": schema_hash,
        },
    )
    await session.execute(
        text("""
        INSERT INTO model_registry(model_id,model_name,status,version)
        VALUES ('signal-quality-champion','signal-quality','champion','legacy-preserved')
        ON CONFLICT (model_id) DO UPDATE SET model_name=EXCLUDED.model_name
    """)
    )
    return {"features": len(features), "datasets": 1, "labels": 1, "models": 1}


async def seed_strategy_registry(session: AsyncSession) -> dict[str, int]:
    # Register only strategies implemented in this repository. New research
    # families remain shadow/declared until code and evidence exist.
    implemented = [
        ("trend_following", "trend"),
        ("mean_reversion", "mean_reversion"),
        ("breakout", "breakout"),
        ("momentum", "momentum"),
        ("scalping", "scalping"),
        ("market_structure", "price_action"),
        ("ict", "ict_smc"),
        ("smc", "ict_smc"),
        ("order_blocks", "ict_smc"),
        ("liquidity_sweeps", "ict_smc"),
        ("vwap", "volume"),
        ("volume_profile", "volume"),
        ("wyckoff", "wyckoff"),
        ("pairs_trading", "statistical"),
        ("statistical_arbitrage", "statistical"),
    ]
    for strategy_id, family in implemented:
        await session.execute(
            text("""
            INSERT INTO strategy_versions(strategy_id,version,family,status,certification)
            VALUES (:strategy_id,'1',:family,'shadow','implemented_requires_evidence')
            ON CONFLICT (strategy_id,version) DO UPDATE SET family=EXCLUDED.family
        """),
            {"strategy_id": strategy_id, "family": family},
        )
    return {"strategies": len(implemented)}


def _instrument_type(kind: str) -> str:
    return {"cash_equity": "equity", "dated_future": "future"}.get(kind, kind)


def _catalogue_symbols(instrument) -> tuple[str, str]:
    """Return canonical and display symbols without inventing USD suffixes.

    Pair markets keep BASE+QUOTE. Equities, indices and commodity aliases use
    the canonical asset registry so GOOGL stays GOOGL, SPX500 becomes US500 and
    BRENT stays BRENT, while metals such as XAUUSD remain paired.
    """
    asset_class = str(instrument.id.asset_class.value or "").lower()
    base = str(instrument.id.base or "").upper()
    quote = str(instrument.id.quote or "").upper()
    pair_symbol = f"{base}{quote}".upper()
    provider_symbol = str(instrument.provider_symbol or pair_symbol).upper().strip()

    if asset_class in {"equity", "index", "commodity"}:
        canonical = str(canonicalize_asset(provider_symbol) or "").upper().strip()
        if not canonical:
            canonical = pair_symbol
    else:
        canonical = pair_symbol

    if asset_class in {"equity", "index"}:
        display = canonical
    elif asset_class == "commodity" and canonical in {"WTI", "BRENT", "NATGAS"}:
        display = canonical
    elif base and quote:
        display = f"{base}/{quote}"
    else:
        display = canonical or base
    return canonical, display


async def persist_instrument_registry(
    session: AsyncSession,
    registry: DynamicInstrumentRegistry,
    *,
    provider_rows: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
) -> dict[str, int]:
    """Persist discovered instruments with bounded executemany round-trips."""
    rows_by_provider = {str(k).lower(): list(v) for k, v in (provider_rows or {}).items()}
    instrument_params: list[dict[str, Any]] = []
    certification_params: list[dict[str, Any]] = []
    mapping_params: list[dict[str, Any]] = []

    for instrument in registry.all():
        key = instrument.canonical_key
        canonical_symbol, display_symbol = _catalogue_symbols(instrument)
        tradable = instrument.status.value == "active"
        instrument_params.append(
            {
                "id": key,
                "symbol": canonical_symbol,
                "display": display_symbol,
                "asset_class": instrument.id.asset_class.value,
                "instrument_type": _instrument_type(instrument.id.kind.value),
                "market_type": "derivative"
                if instrument.id.kind.value in {"perpetual", "dated_future", "option", "cfd"}
                else "cash",
                "base": instrument.id.base,
                "quote": instrument.id.quote,
                "settlement": instrument.id.settlement,
                "underlying": instrument.id.base,
                "multiplier": float(instrument.contract_multiplier),
                "tick": float(instrument.tick_size) if instrument.tick_size is not None else None,
                "step": float(instrument.quantity_step) if instrument.quantity_step is not None else None,
                "min_qty": float(instrument.minimum_quantity) if instrument.minimum_quantity is not None else None,
                "min_notional": float(instrument.minimum_notional) if instrument.minimum_notional is not None else None,
                "inverse": instrument.linear_or_inverse == "inverse",
                "timezone": instrument.timezone,
                "active": instrument.status.value == "active",
                "tradable": tradable,
            }
        )
        certification_params.append(
            {
                "id": key,
                "evidence": _json({"source": "provider_discovery", "not_public_delivery_certified": True}),
            }
        )

    for provider, source_rows in rows_by_provider.items():
        by_symbol = {str(r.get("provider_symbol") or r.get("symbol") or "").upper(): r for r in source_rows}
        for instrument in registry.by_provider(provider):
            raw = by_symbol.get(str(instrument.provider_symbol or "").upper(), {})
            capabilities = set(raw.get("capabilities") or ())
            provider_instrument_id = str(
                raw.get("provider_instrument_id") or raw.get("id") or instrument.provider_symbol
            )
            mapping_params.append(
                {
                    "provider": provider,
                    "venue": instrument.venue,
                    "symbol": instrument.provider_symbol,
                    "provider_id": provider_instrument_id,
                    "canonical_id": instrument.canonical_key,
                    "status": instrument.status.value,
                    "trading": instrument.status.value == "active",
                    "candles": "historical_ohlc" in capabilities,
                    "quotes": "live_quotes" in capabilities,
                    "book": bool({"order_book_l1", "order_book_l2", "order_book_l3"} & capabilities),
                    "trades": "trades" in capabilities,
                    "funding": "funding" in capabilities,
                    "oi": "open_interest" in capabilities,
                    "metadata": _json(raw.get("metadata") or {}),
                }
            )

    if instrument_params:
        await session.execute(
            text("""
            INSERT INTO instruments(
              instrument_id,canonical_symbol,display_symbol,asset_class,instrument_type,
              market_type,base_currency,quote_currency,settlement_currency,underlying,
              contract_multiplier,tick_size,quantity_step,minimum_quantity,minimum_notional,
              inverse_contract,trading_timezone,active,tradable,discovery_status,
              last_discovered_at,last_verified_at,updated_at
            ) VALUES (
              :id,:symbol,:display,:asset_class,:instrument_type,:market_type,
              :base,:quote,:settlement,:underlying,:multiplier,:tick,:step,:min_qty,
              :min_notional,:inverse,:timezone,:active,:tradable,'metadata_validated',NOW(),NOW(),NOW()
            ) ON CONFLICT (instrument_id) DO UPDATE SET
              canonical_symbol=EXCLUDED.canonical_symbol, display_symbol=EXCLUDED.display_symbol,
              asset_class=EXCLUDED.asset_class, instrument_type=EXCLUDED.instrument_type,
              base_currency=EXCLUDED.base_currency, quote_currency=EXCLUDED.quote_currency,
              settlement_currency=EXCLUDED.settlement_currency,
              contract_multiplier=EXCLUDED.contract_multiplier,
              active=EXCLUDED.active, tradable=EXCLUDED.tradable,
              discovery_status=EXCLUDED.discovery_status,
              last_discovered_at=NOW(), last_verified_at=NOW(), updated_at=NOW()
        """),
            instrument_params,
        )
        await session.execute(
            text("""
            INSERT INTO instrument_certifications(instrument_id,readiness_state,evidence,certified_at,updated_at)
            VALUES (:id,'metadata_validated',CAST(:evidence AS JSONB),NOW(),NOW())
            ON CONFLICT (instrument_id) DO UPDATE SET
              readiness_state=EXCLUDED.readiness_state,evidence=EXCLUDED.evidence,updated_at=NOW()
        """),
            certification_params,
        )

    if mapping_params:
        await session.execute(
            text("""
            INSERT INTO provider_instruments(
              provider,venue,provider_symbol,provider_instrument_id,canonical_instrument_id,
              market_status,trading_enabled,data_enabled,execution_enabled,
              historical_candles_supported,live_quotes_supported,order_book_supported,
              trades_supported,funding_supported,open_interest_supported,provider_metadata,
              last_seen_at,last_successful_refresh_at
            ) VALUES (
              :provider,:venue,:symbol,:provider_id,:canonical_id,:status,:trading,TRUE,FALSE,
              :candles,:quotes,:book,:trades,:funding,:oi,CAST(:metadata AS JSONB),NOW(),NOW()
            ) ON CONFLICT (provider,venue,provider_instrument_id) DO UPDATE SET
              provider_symbol=EXCLUDED.provider_symbol,
              canonical_instrument_id=EXCLUDED.canonical_instrument_id,
              market_status=EXCLUDED.market_status,
              trading_enabled=EXCLUDED.trading_enabled,
              data_enabled=TRUE,
              provider_metadata=EXCLUDED.provider_metadata,
              last_seen_at=NOW(),last_successful_refresh_at=NOW(),delisted_at=NULL
        """),
            mapping_params,
        )

    return {
        "instruments": len(instrument_params),
        "provider_mappings": len(mapping_params),
    }


async def record_discovery_run(session: AsyncSession, provider: str, result: Mapping[str, Any]) -> None:
    await session.execute(
        text("""
        INSERT INTO instrument_discovery_runs(
          provider,duration_ms,discovered,created,updated,unchanged,mapping_failures,state,reason
        ) VALUES (:provider,:duration_ms,:discovered,:created,:updated,:unchanged,:failures,:state,:reason)
    """),
        {
            "provider": provider,
            "duration_ms": float(result.get("duration_ms") or 0),
            "discovered": int(result.get("discovered") or 0),
            "created": int(result.get("created") or 0),
            "updated": int(result.get("updated") or 0),
            "unchanged": int(result.get("unchanged") or 0),
            "failures": int(result.get("mapping_failures") or 0),
            "state": str(result.get("state") or "ok"),
            "reason": str(result.get("reason") or "")[:255] or None,
        },
    )


async def verify_ecosystem_bootstrap(
    session: AsyncSession,
    *,
    require_instruments: bool = False,
) -> dict[str, Any]:
    """Read back the persisted catalogue and fail closed on partial bootstrap.

    The source declarations are not accepted as proof here: counts come from
    PostgreSQL after the seed statements have executed in the current
    transaction.
    """

    async def scalar(sql: str) -> int:
        value = await session.scalar(text(sql))
        return int(value or 0)

    counts = {
        "active_products": await scalar("SELECT COUNT(*) FROM subscription_products WHERE active=TRUE"),
        "active_prices": await scalar("SELECT COUNT(*) FROM subscription_prices WHERE effective_until IS NULL"),
        "feature_entitlements": await scalar(
            "SELECT COUNT(*) FROM subscription_entitlements WHERE entitlement_key LIKE 'feature.%' AND enabled=TRUE"
        ),
        "control_entitlements": await scalar(
            "SELECT COUNT(*) FROM subscription_entitlements WHERE entitlement_key NOT LIKE 'feature.%'"
        ),
        "feature_definitions": await scalar("SELECT COUNT(*) FROM feature_definitions WHERE feature_version='3'"),
        "label_versions": await scalar("SELECT COUNT(*) FROM label_versions"),
        "dataset_versions": await scalar("SELECT COUNT(*) FROM dataset_versions"),
        "model_registry": await scalar("SELECT COUNT(*) FROM model_registry"),
        "strategy_versions": await scalar("SELECT COUNT(*) FROM strategy_versions"),
        "instruments": await scalar("SELECT COUNT(*) FROM instruments WHERE active=TRUE"),
        "tradable_instruments": await scalar("SELECT COUNT(*) FROM instruments WHERE active=TRUE AND tradable=TRUE"),
        "provider_mappings": await scalar("SELECT COUNT(*) FROM provider_instruments WHERE data_enabled=TRUE"),
    }
    expected_feature_entitlements = sum(
        len(get_entitlements(tier).features) for tier in TIER_ORDER if tier not in {Tier.ADMIN, Tier.OWNER}
    )
    expected_control_entitlements = 16 * len([tier for tier in TIER_ORDER if tier not in {Tier.ADMIN, Tier.OWNER}])
    expected_feature_definitions = len(get_feature_columns())
    blockers: list[str] = []
    minimums = {
        "active_products": 6,
        "active_prices": 6,
        "feature_entitlements": expected_feature_entitlements,
        "control_entitlements": expected_control_entitlements,
        "feature_definitions": expected_feature_definitions,
        "label_versions": 1,
        "dataset_versions": 1,
        "model_registry": 1,
        "strategy_versions": 15,
    }
    for key, minimum in minimums.items():
        if counts[key] < minimum:
            blockers.append(f"{key}:{counts[key]}<{minimum}")
    if require_instruments and counts["tradable_instruments"] < 1:
        blockers.append("tradable_instruments:0<1")
    if require_instruments and counts["provider_mappings"] < 1:
        blockers.append("provider_mappings:0<1")
    return {
        "ok": not blockers,
        "catalogue_version": CATALOGUE_VERSION,
        "counts": counts,
        "minimums": minimums,
        "require_instruments": bool(require_instruments),
        "blockers": blockers,
    }


async def seed_all(session: AsyncSession) -> dict[str, Any]:
    result: dict[str, Any] = {"catalogue_version": CATALOGUE_VERSION}
    result["subscriptions"] = await seed_subscription_catalogue(session)
    result["ml"] = await seed_ml_governance(session)
    result["strategies"] = await seed_strategy_registry(session)
    return result

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_environment_prefers_railway_metadata(monkeypatch):
    from core.env import runtime_environment_name

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
    assert runtime_environment_name() == "staging"


def test_scheduler_lease_is_project_environment_scoped_not_service_scoped(monkeypatch):
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "project-id")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
    monkeypatch.setenv("RAILWAY_SERVICE_ID", "service-id")
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "deployment-id")

    from core.job_leases import scheduler_job_scope

    scope = scheduler_job_scope("resend_unsent_signals")
    assert scope == "project-id:staging:resend_unsent_signals"
    assert "service-id" not in scope
    assert "deployment-id" not in scope


def test_postgres_lease_releases_explicitly_and_does_not_wrap_job_body():
    source = (ROOT / "core/job_leases.py").read_text("utf-8")
    assert "SELECT pg_try_advisory_lock" in source
    assert "SELECT pg_advisory_unlock" in source
    assert "if postgres_available and connection is not None:" in source


def test_performance_ledger_uses_atomic_conflict_handling():
    source = (ROOT / "services/performance_ledger.py").read_text("utf-8")
    assert "pg_insert(PerformanceLedgerEntry).values(pending)" in source
    assert 'constraint="uq_performance_ledger_scope"' in source
    assert "snapshot_hash.is_distinct_from" in source
    assert 'runtime_environment_name("development")' in source


def test_background_jobs_are_bounded_leased_and_coalesced():
    source = (ROOT / "signalrank_telegram/bot.py").read_text("utf-8")
    for marker in (
        'RESEND_JOB_BUDGET_SECONDS", "20"',
        'OUTCOME_NOTIFICATION_JOB_BUDGET_SECONDS", "45"',
        'OUTCOME_NOTIFICATION_MAX_OUTCOMES_PER_RUN", "5"',
        'RESEND_MAX_USERS_PER_RUN", "6"',
        'RESEND_MAX_SIGNALS", "3"',
        'RESEND_UNSENT_INTERVAL_SECONDS", "60"',
        'OUTCOME_NOTIFICATION_INTERVAL_SECONDS", "90"',
        'RESEND_UNSENT_JOB_ENABLED',
        'acquire_scheduler_job_lease("resend_unsent_signals"',
        'acquire_scheduler_job_lease("outcome_notifications"',
        'standby: active delivery owner holds lease',
    ):
        assert marker in source


def test_metals_and_fx_route_to_broker_native_provider_when_configured(monkeypatch):
    monkeypatch.setenv("META_API_TOKEN", "token")
    monkeypatch.setenv("META_API_MARKET_DATA_ACCOUNT_ID", "account")
    from data.get_live_price import _get_providers_for_asset

    assert _get_providers_for_asset("XAGUSD")[0] == "metaapi"
    assert _get_providers_for_asset("EURUSD")[0] == "metaapi"


def test_unconfigured_keyed_providers_do_not_consume_quote_budget(monkeypatch):
    for name in (
        "META_API_TOKEN", "META_API_MARKET_DATA_ACCOUNT_ID", "META_API_ACCOUNT_ID",
        "METAAPI_ACCOUNT_ID", "OANDA_API_KEY", "OANDA_TOKEN", "OANDA_ACCOUNT_ID",
        "TWELVEDATA_API_KEY", "TWELVE_DATA_API_KEY", "FCS_API_KEY", "FCS_API_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("TELEGRAM_OWNER_ID", raising=False)
    monkeypatch.delenv("OWNER_TELEGRAM_ID", raising=False)
    monkeypatch.delenv("OWNER_IDS", raising=False)

    from data.get_live_price import _get_providers_for_asset

    assert _get_providers_for_asset("XAGUSD") == ["yahoo"]
    assert _get_providers_for_asset("EURUSD") == ["yahoo"]


def test_production_readiness_exposes_fail_closed_provider_coverage():
    source = (ROOT / "railway_main.py").read_text("utf-8")
    assert "async def _provider_coverage_readiness_check" in source
    assert '"provider_coverage": provider_coverage' in source
    assert 'complete = bool(configured_trusted)' in source
    assert '"ok": complete if production else True' in source


def test_fcs_v4_quote_contract_is_parsed(monkeypatch):
    import asyncio
    import time
    import requests

    class Response:
        ok = True
        status_code = 200

        @staticmethod
        def json():
            return {
                "status": True,
                "response": [
                    {
                        "ticker": "SILVER",
                        "active": {
                            "a": 28.12,
                            "b": 28.10,
                            "c": 28.11,
                            "t": int(time.time()),
                        },
                    }
                ],
            }

    monkeypatch.setenv("FCS_API_KEY", "test-key")
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: Response())

    from data.get_live_price import _fetch_fcs_quote, _price_breakers
    from data.provider_types import LivePriceQuote

    _price_breakers.pop("fcs", None)
    quote = asyncio.run(_fetch_fcs_quote("XAGUSD"))
    assert isinstance(quote, LivePriceQuote)
    assert quote.provider == "fcs"
    assert quote.bid == 28.10
    assert quote.ask == 28.12
    assert quote.price == 28.11


def test_provider_coverage_gate_is_nonblocking_in_staging_and_fail_closed_in_production(monkeypatch):
    import ast
    import asyncio
    import os
    import data.get_live_price as live_price

    source = (ROOT / "railway_main.py").read_text("utf-8")
    tree = ast.parse(source)
    helper_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "_provider_coverage_readiness_check"
    )
    namespace = {"os": os}
    exec(compile(ast.Module(body=[helper_node], type_ignores=[]), "railway_main.py", "exec"), namespace)
    helper = namespace["_provider_coverage_readiness_check"]

    monkeypatch.setenv("ENABLED_ASSET_CLASSES", "fx,commodity")
    monkeypatch.delenv("META_API_MARKET_DATA_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("META_API_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("METAAPI_ACCOUNT_ID", raising=False)
    monkeypatch.setattr(live_price, "_get_providers_for_asset", lambda symbol: ["yahoo"])

    # Deterministic discovery state: without a verified snapshot the
    # production gate must fail closed regardless of any local DB rows.
    import data.pair_discovery as pair_discovery

    monkeypatch.setattr(
        pair_discovery,
        "get_asset_discovery_snapshot",
        lambda force_refresh=False: {
            "total": 0,
            "last_refresh_age_seconds": 10**12,
            "untrusted_total": 0,
            "providers": {},
        },
    )

    staging = asyncio.run(helper(production=False))
    production = asyncio.run(helper(production=True))
    assert staging["ok"] is True
    assert staging["complete"] is False
    assert production["ok"] is False
    assert "missing_provider_classes:commodity,fx" in production["detail"]
    assert "asset_discovery_unverified" in production["detail"]

    monkeypatch.setenv("META_API_MARKET_DATA_ACCOUNT_ID", "dedicated-account")
    monkeypatch.setattr(live_price, "_get_providers_for_asset", lambda symbol: ["metaapi", "yahoo"])
    import data.pair_discovery as pair_discovery
    monkeypatch.setattr(
        pair_discovery,
        "get_asset_discovery_snapshot",
        lambda force_refresh=False: {
            "total": 10,
            "last_refresh_age_seconds": 5,
            "untrusted_total": 0,
            "providers": {"provider_backed": True},
        },
    )
    production = asyncio.run(helper(production=True))
    assert production["ok"] is True
    assert production["complete"] is True

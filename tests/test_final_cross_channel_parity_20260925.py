from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_final_schema_head_includes_account_execution_policy_revision() -> None:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "db" / "migrations"))
    assert ScriptDirectory.from_config(cfg).get_heads() == [
        "0045_mt5_credential_retirement"
    ]
    migration = source(
        "db/migrations/versions/0040_cross_channel_paper_receipts.py"
    )
    assert 'revision = "0040_cross_channel_paper_receipt"' in migration
    assert len("0040_cross_channel_paper_receipt") <= 32
    assert 'down_revision = "0039_web_signup_acquisition"' in migration
    assert "ALTER COLUMN delivery_id DROP NOT NULL" in migration
    broker = source("db/migrations/versions/0041_broker_connection_registry.py")
    assert 'revision = "0041_broker_connection_registry"' in broker
    assert 'down_revision = "0040_cross_channel_paper_receipt"' in broker
    recovery = source("db/migrations/versions/0042_ml_starvation_recovery_provenance.py")
    assert 'revision = "0042_ml_recovery_provenance"' in recovery
    assert 'down_revision = "0041_broker_connection_registry"' in recovery
    account_policy = source("db/migrations/versions/0043_account_execution_policy.py")
    assert 'revision = "0043_account_execution_policy"' in account_policy
    assert 'down_revision = "0042_ml_recovery_provenance"' in account_policy
    assert "trading_account_policies" in account_policy
    assert "broker_reconciliation_state" in account_policy
    assert "trading_account_ledger_entries" in account_policy
    assert "trg_trading_account_ledger_immutable" in account_policy
    assert "prevent_trading_account_ledger_mutation" in account_policy
    assert "uq_trading_account_ledger_provider_event" in account_policy
    assert "broker_execution_decisions" in account_policy
    for field in (
        "max_weekly_loss_pct",
        "max_spread_bps",
        "max_slippage_bps",
        "min_confidence",
        "min_expected_rr",
        "external_max_weekly_loss_pct",
        "allowed_strategies",
        "trading_windows",
        "certified_by_user_id",
        "certified_by_authority",
    ):
        assert field in account_policy
    assert '"broker_executions"' in account_policy
    assert '"mt5_executions"' in account_policy
    assert '"connection_id"' in account_policy


def test_paper_is_free_education_but_live_features_remain_paid() -> None:
    policy = source("core/tier_policy.py")
    basic = policy[
        policy.index("_BASIC_FEATURES"):
        policy.index("_PREMIUM_FEATURES")
    ]
    minimums = policy[
        policy.index("FEATURE_MINIMUM_TIER"):
        policy.index("FEATURE_VALUE")
    ]
    assert '"paper_trading"' in basic
    assert '"paper_trading": Tier.FREE' in minimums
    assert '"broker_connection": Tier.PREMIUM' in minimums
    assert '"execution_preflight": Tier.VIP' in minimums
    assert '"risk_sizing": Tier.VIP' in minimums


def test_web_paper_controls_are_canonical_and_no_telegram_link_is_required() -> None:
    api = source("web/platform_api.py")
    app = source("web/platform_app/app.js")
    paper = api[
        api.index('@router.get("/paper")'):
        api.index('@router.get("/instruments/search")')
    ]
    assert 'user_identity="platform"' in paper
    assert "_telegram_identity_or_409" not in api
    assert "Your account does not need Telegram to use web paper trading." in app
    assert "Telegram link required for automatic paper controls." not in app


def test_web_travel_mode_is_round_tripped_through_canonical_identity() -> None:
    identity = source("services/platform/identity.py")
    api = source("web/platform_api.py")
    html = source("web/platform_app/index.html")
    app = source("web/platform_app/app.js")
    snapshot = identity[
        identity.index("async def user_snapshot"):
        identity.index("@dataclass", identity.index("async def user_snapshot"))
    ]
    assert "timezone_auto_update" in snapshot
    assert "timezone_updated_at" in snapshot
    assert "timezone_auto_update: bool | None = None" in api
    profile = api[
        api.index('@router.patch("/profile")'):
        api.index('@router.get("/trading-profile")')
    ]
    assert '"timezone_auto_update"' in profile
    assert 'name="timezone_auto_update"' in html
    assert "timezone_auto_update:Boolean" in app


def test_referral_claims_use_successful_attributions_only() -> None:
    api = source("web/platform_api.py")
    telegram = source("signalrank_telegram/commands.py")
    web_summary = api[
        api.index('@router.get("/referrals")'):
        api.index('@router.post("/account/telegram-link")')
    ]
    assert "is_successful IS TRUE" in web_summary
    assert '"total_attributions": total_attributions' in web_summary
    leaderboard = api[
        api.index('@router.get("/referrals/leaderboard")'):
        api.index('@router.post("/account/telegram-link")')
    ]
    assert "r.is_successful IS TRUE" in leaderboard
    tg = telegram[
        telegram.index("async def referral_leaderboard_command"):
        telegram.index("async def referral_rewards_command")
    ]
    assert "ReferralAttribution.is_successful.is_(True)" in tg


def test_subscription_cancel_is_shared_and_never_immediate_downgrade() -> None:
    service = source("services/subscription_cancellation.py")
    telegram = source("signalrank_telegram/commands.py")
    api = source("web/platform_api.py")
    assert "cancel_auto_renew_for_user" in service
    assert "user.auto_renew = False" in service
    assert "user.tier =" not in service
    assert "subscription.status =" not in service
    assert "cancel_auto_renew_for_telegram_user" in telegram
    endpoint = api[
        api.index('@router.post("/billing/cancel-auto-renew")'):
        api.index('@router.post("/billing/refund-request", status_code=201)')
    ]
    assert "payload.confirm is not True" in endpoint
    assert "cancel_auto_renew_for_user" in endpoint
    assert "does not issue a refund" in endpoint
    assert "provider_follow_up_required" in endpoint
    assert "create_support_ticket" in endpoint


def test_subscription_cancel_releases_db_before_provider_network_io() -> None:
    service = source("services/subscription_cancellation.py")
    fn = service[
        service.index("async def cancel_auto_renew_for_user"):
        service.index("async def cancel_auto_renew_for_telegram_user")
    ]
    snapshot_rollback = fn.index("await session.rollback()")
    provider_call = fn.index("await _disable_paystack_subscription")
    commit_label = fn.index('label="subscription.cancel_commit"')
    assert snapshot_rollback < provider_call < commit_label
    assert ".with_for_update()" not in fn[:provider_call]


def test_refund_review_is_account_scoped_and_never_automatic() -> None:
    api = source("web/platform_api.py")
    endpoint = api[
        api.index('@router.post("/billing/refund-request"'):
        api.index('@router.get("/notifications")')
    ]
    assert "payment_receipts WHERE user_id=:uid" in endpoint
    assert "payment_events WHERE user_id=:uid" in endpoint
    assert "subscriptions WHERE user_id=:uid" in endpoint
    assert '"automatic_refund": False' in endpoint
    assert "create_support_ticket" in endpoint
    assert "refund(" not in endpoint.lower()


def test_vip_execution_webhook_uses_safe_destination_validation() -> None:
    api = source("web/platform_api.py")
    block = api[
        api.index('@router.get("/execution-webhook")'):
        api.index('@router.get("/webhooks")')
    ]
    assert '_assert_command(user, "setwebhook")' in block
    assert "validate_webhook_destination" in block
    assert "user_webhooks" in block
    assert '@router.delete("/execution-webhook")' in block


def test_delivered_history_simulation_has_no_invented_default_performance() -> None:
    api = source("web/platform_api.py")
    block = api[
        api.index('@router.post("/simulation")'):
        api.index('@router.get("/elite-signals")')
    ]
    assert '_assert_command(user, "simulate")' in block
    assert 'user_identity="platform"' in block
    assert "delivered_r_samples" in block
    assert "SIMULATION_MIN_CONFIRMED_OUTCOMES" in block
    assert '"ready": False' in block
    assert "No default win rate or invented reward assumption" in block
    assert "monte_carlo_monthly_projection" in block
    assert "not a profit forecast or guarantee" in block


def test_elite_signals_are_receipt_scoped_on_web_and_telegram() -> None:
    api = source("web/platform_api.py")
    telegram = source("signalrank_telegram/commands.py")
    web = api[
        api.index('@router.get("/elite-signals")'):
        api.index('@router.get("/quality")')
    ]
    assert "signal_deliveries" in web
    assert "notification_events" in web
    assert "s.score>=85" in web
    assert "LIMIT 5" in web
    tg = telegram[
        telegram.index("async def elite_command"):
        telegram.index("async def early_command")
    ]
    assert "SignalDelivery.sent_ok.is_(True)" in tg
    assert "SignalDelivery.telegram_chat_id.is_not(None)" in tg
    assert "SignalDelivery.telegram_message_id.is_not(None)" in tg
    assert "Signal.score >= 85.0" in tg
    assert ".limit(5)" in tg


def test_auto_and_copy_execution_use_stricter_automation_risk_cap() -> None:
    router = source("services/mt5_signal_router.py")
    call = router[
        router.index("volume = await self._calculate_position_size("):
        router.index("volume = self._apply_position_weight", router.index("volume = await self._calculate_position_size("))
    ]
    assert "execution_mode=execution_mode" in call
    sizing = router[
        router.index("async def _calculate_position_size"):
        router.index("async def _sync_to_paper_ledger")
    ]
    assert 'execution_mode: str = "manual"' in sizing
    assert 'mode in {"auto", "copy", "copy_trade"}' in sizing
    assert 'os.getenv("AUTO_MAX_RISK_CAP_PCT", "3.0")' in sizing
    assert "max_risk_pct = min(" in sizing


def test_web_ui_exposes_final_parity_controls_without_tier_breakage() -> None:
    html = source("web/platform_app/index.html")
    app = source("web/platform_app/app.js")
    for marker in (
        'id="vipResearchPanel"',
        'id="simulationForm"',
        'id="eliteSignalList"',
        'id="referralLeaderboard"',
        'id="cancelAutoRenewButton"',
        'id="refundReviewForm"',
        'id="executionWebhookPanel"',
        'name="timezone_auto_update"',
    ):
        assert marker in html
    for route in (
        "/simulation",
        "/elite-signals",
        "/referrals/leaderboard",
        "/billing/cancel-auto-renew",
        "/billing/refund-request",
        "/execution-webhook",
    ):
        assert route in app
    assert "async function loadVipResearch()" in app
    assert "async function loadExecutionWebhook()" in app


def test_pwa_shell_cache_rotated_for_final_parity_release() -> None:
    worker = source("web/platform_app/service-worker.js")
    assert "signalrank-shell-v" in worker


def test_web_multi_account_policy_editor_exposes_hard_risk_controls() -> None:
    html = source("web/platform_app/index.html")
    app = source("web/platform_app/app.js")
    api = source("web/platform_api.py")
    for marker in (
        'id="brokerPolicyEditor"',
        'name="account_mode"',
        'name="execution_permission"',
        'name="max_risk_per_trade_pct"',
        'name="max_daily_loss_pct"',
        'name="max_weekly_loss_pct"',
        'name="max_total_drawdown_pct"',
        'name="max_spread_bps"',
        'name="max_slippage_bps"',
        'name="min_confidence"',
        'name="min_expected_rr"',
        'name="allowed_strategies"',
        'name="trading_days"',
        'name="prop_rules_version"',
        'name="external_rules_json"',
    ):
        assert marker in html
    assert "openBrokerPolicy" in app
    assert "brokerPolicyPayload" in app
    assert "JSON.stringify(p.external_rules||{},null,2)" in app
    assert "external_rules:externalRules" in app
    assert "/safety-freeze" in app
    assert "/ledger?limit=50" in app
    assert 'id="brokerAccountLedger"' in html
    assert '@router.get("/broker/connections/{connection_id}/policy")' in api
    assert '@router.get("/broker/connections/{connection_id}/ledger")' in api
    assert '@router.put("/broker/connections/{connection_id}/policy")' in api
    assert '@router.post("/broker/connections/{connection_id}/safety-freeze")' in api


def test_prop_policy_certification_is_privileged_versioned_and_audited() -> None:
    api = source("web/platform_api.py")
    service = source("services/account_policies.py")
    models = source("db/models.py")
    assert '@router.post("/admin/broker/connections/{connection_id}/prop-certification")' in api
    assert "_platform_operator_authority(user)" in api
    assert "expected_policy_version" in api
    assert "certified_by_user_id=int(user[\"id\"])" in api
    assert "prop_certification_operator_required" in service
    assert "policy_version_changed" in service
    assert 'event_type="prop_policy_certified"' in service
    assert "certified_by_user_id" in models
    assert "certified_by_authority" in models
    configure = service[
        service.index("async def configure_account_policy"):
        service.index("async def certify_prop_policy")
    ]
    assert "row.certified_by_user_id = None" in configure
    assert "row.certified_by_authority = None" in configure


def test_account_policy_changes_and_safety_blocks_are_durably_audited() -> None:
    service = source("services/account_policies.py")
    configure = service[
        service.index("async def configure_account_policy"):
        service.index("async def certify_prop_policy")
    ]
    freeze = service[
        service.index("async def set_account_frozen"):
        service.index("async def reconciliation_snapshot")
    ]
    reconcile = service[
        service.index("async def record_reconciliation"):
        service.index("async def evaluate_persisted_account_policy")
    ]

    assert 'event_type="account_policy_configured"' in configure
    assert '"policy_version": int(row.policy_version)' in configure
    assert '"hard_rule_count": len(' in configure
    assert '"execution_disabled": True' in configure
    assert "connection.execution_enabled = False" in configure

    assert '"account_policy_safety_frozen"' in freeze
    assert '"account_policy_safety_unfrozen"' in freeze
    assert '"execution_disabled": True' in freeze

    assert 'event_type="account_reconciliation_safety_block"' in reconcile
    assert 'normalized in {"DEGRADED", "FROZEN", "AUTH_EXPIRED", "DISCONNECTED"}' in reconcile
    assert "connection.execution_enabled = False" in reconcile
    assert '"discrepancy_code": (' in reconcile


def test_prop_hard_rule_engine_is_generic_versioned_and_exactly_explainable() -> None:
    policy = source("core/account_policy.py")
    mt5 = source("services/mt5_signal_router.py")
    bybit = source("services/bybit_signal_router.py")

    assert "PROP_HARD_RULE_TYPES" in policy
    assert "def validate_prop_rule_config" in policy
    assert "def _evaluate_prop_hard_rules" in policy
    assert 'prefix = f"prop_rule:{rule_id}"' in policy
    assert "unsupported_prop_hard_rule" in policy
    assert 'order_size_unit="LOT"' in mt5
    assert 'order_size_unit="BASE_UNITS"' in bybit


def test_canonical_account_ledger_is_append_only_account_scoped_and_provider_authoritative() -> None:
    migration = source("db/migrations/versions/0043_account_execution_policy.py")
    model = source("db/models.py")
    service = source("services/trading_account_ledger.py")
    mt5 = source("services/mt5_signal_router.py")
    mt5_client = source("services/mt5_client.py")
    mt5_reconciler = source("services/mt5_reconciler.py")
    worker = source("worker/worker.py")
    bybit = source("services/bybit_signal_router.py")
    reconciler = source("services/bybit_reconciler.py")

    assert "trading_account_ledger_entries" in migration
    assert "BEFORE UPDATE OR DELETE" in migration
    assert "uq_trading_account_ledger_provider_event" in migration
    assert "class TradingAccountLedgerEntry" in model
    assert "BrokerConnection.user_id == int(user_id)" in service
    assert "BrokerConnection.connection_id == str(connection_id)" in service
    assert "on_conflict_do_nothing" in service
    assert "_safe_metadata" in service
    assert 'entry_type="order"' in mt5
    assert "/history-deals/ticket/" in mt5_client
    assert "/history-deals/position/" in mt5_client
    assert "DEAL_ENTRY_OUT" in mt5_reconciler
    assert "_append_account_ledger_in_session" in mt5_reconciler
    assert "mt5_reconciliation_loop" in worker
    assert 'entry_type="order"' in bybit
    assert '"entry_type": "realized_pnl"' in reconciler
    assert '"entry_type": "fee"' in reconciler
    assert "broker_values_authoritative" in source("web/platform_api.py")


def test_broker_performance_is_composed_per_account_not_mixed_headline() -> None:
    api = source("web/platform_api.py")
    app = source("web/platform_app/app.js")
    block = api[
        api.index('@router.get("/broker")'):
        api.index('@router.post("/broker/mt5")')
    ]
    assert "mt5_account_stats" in block
    assert "provider_account_stats" in block
    assert '"metric_scope": "single_account"' in block
    assert '"composition_required": True' in block
    assert '"mixed_account_diagnostics"' in block
    assert "accountStats=data.stats?.accounts||[]" in app
    assert "accountStatsById" in app
    assert "Performance scope','Per account only" in app
    assert "Demo, personal-live and PROP performance are not combined" in app
    assert "data.stats?.mt5" not in app
    assert "data.stats?.providers" not in app


def test_0044_broker_credential_envelope_schema_and_runtime_contract() -> None:
    migration = source("db/migrations/versions/0044_broker_credential_envelope.py")
    models = source("db/models.py")
    schema_gate = source("scripts/assert_database_schema.py")
    readiness = source("railway_main.py")
    credentials = source("services/broker_credentials.py")

    assert 'revision = "0044_broker_credential_envelope"' in migration
    assert 'down_revision = "0043_account_execution_policy"' in migration
    for marker in (
        "credential_format",
        "credential_version",
        "credential_key_id",
        "credential_revision",
        "credential_rotated_at",
    ):
        assert marker in migration
        assert marker in models
        assert marker in schema_gate
        assert marker in readiness
    assert "legacy_fernet" in migration
    assert "BROKER_CREDENTIAL_KEYRING_JSON" in credentials
    assert "BROKER_CREDENTIAL_ACTIVE_KEY_ID" in credentials
    assert "broker credential envelope account binding mismatch" in credentials


def test_0045_mt5_credential_retirement_schema_and_runtime_contract() -> None:
    migration = source(
        "db/migrations/versions/0045_mt5_legacy_credential_retirement.py"
    )
    models = source("db/models.py")
    schema_gate = source("scripts/assert_database_schema.py")
    staging_proof = source("scripts/staging_runtime_proof.py")
    readiness = source("railway_main.py")
    mt5 = source("services/mt5_client.py")

    assert 'revision = "0045_mt5_credential_retirement"' in migration
    assert 'down_revision = "0044_broker_credential_envelope"' in migration
    assert "password_encrypted" in migration
    assert "nullable=True" in migration
    assert "canonical.credential_format = 'envelope_v1'" in migration
    assert "password_encrypted = NULL" in migration
    assert "mt5_credentials_password_nullable" in schema_gate
    assert "mt5_credentials_password_nullable" in staging_proof
    assert "mt5_credentials_password_nullable" in readiness
    assert "password_encrypted: Mapped[Optional[str]]" in models
    assert "_sync_mt5_compatibility_metadata" in mt5

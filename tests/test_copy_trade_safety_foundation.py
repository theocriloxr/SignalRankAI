from __future__ import annotations

from pathlib import Path

from services.ecosystem_policy import ConsentRecord, copy_trade_decision


ROOT = Path(__file__).resolve().parents[1]


def test_copy_trade_is_fail_closed_without_every_required_boundary() -> None:
    blocked = copy_trade_decision(
        enabled=False,
        consent=None,
        leader_event_id=None,
        risk_allowed=False,
        kill_switch=True,
        duplicate=True,
    )
    assert blocked.allowed is False
    assert blocked.code == "COPY_BLOCKED"
    assert set(blocked.reasons) == {
        "COPY_TRADE_DISABLED",
        "explicit_copy_consent_required",
        "leader_provenance_required",
        "risk_cap_blocked",
        "kill_switch_enabled",
        "duplicate_event",
    }


def test_copy_trade_requires_active_copy_specific_consent() -> None:
    wrong_mode = ConsentRecord(
        user_id=7,
        mode="auto",
        accepted=True,
        accepted_at="2026-09-26T00:00:00Z",
    )
    revoked = ConsentRecord(
        user_id=7,
        mode="copy_trade",
        accepted=True,
        accepted_at="2026-09-26T00:00:00Z",
        revoked_at="2026-09-26T01:00:00Z",
    )
    for consent in (wrong_mode, revoked):
        decision = copy_trade_decision(
            enabled=True,
            consent=consent,
            leader_event_id="leader-event-1",
            risk_allowed=True,
        )
        assert decision.allowed is False
        assert "explicit_copy_consent_required" in decision.reasons


def test_copy_trade_allows_only_complete_safe_intent() -> None:
    consent = ConsentRecord(
        user_id=7,
        mode="copy_trade",
        accepted=True,
        accepted_at="2026-09-26T00:00:00Z",
    )
    decision = copy_trade_decision(
        enabled=True,
        consent=consent,
        leader_event_id="leader-event-1",
        risk_allowed=True,
        kill_switch=False,
        duplicate=False,
    )
    assert decision.allowed is True
    assert decision.code == "COPY_ALLOWED"
    assert decision.reasons == ()


def test_execution_gate_keeps_copy_mode_behind_global_consent_and_risk() -> None:
    source = (ROOT / "execution" / "service.py").read_text(encoding="utf-8")
    assert 'mode == "copy_trade" and not self.safety_flags.copy_trade_enabled' in source
    assert 'reasons.append("COPY_TRADE_DISABLED")' in source
    assert "if not request.consent:" in source
    assert 'reasons.append("user_consent_required")' in source
    assert "if not request.risk_allowed:" in source
    assert 'reasons.append("risk_policy_blocked")' in source


def test_broker_routers_require_user_copy_mode_and_account_specific_risk() -> None:
    bybit = (ROOT / "services" / "bybit_signal_router.py").read_text(encoding="utf-8")
    mt5 = (ROOT / "services" / "mt5_signal_router.py").read_text(encoding="utf-8")

    assert 'configured_mode != "copy_trade"' in bybit
    assert "profile_copy_disabled" in bybit
    assert "AccountRiskSnapshot(" in bybit
    assert "evaluate_persisted_account_policy(" in bybit
    assert "connection_id=str(connection.connection_id)" in bybit

    assert "ExecutionMode.COPY_TRADE" in mt5
    assert "profile_copy_disabled" in mt5
    assert "AccountRiskSnapshot(" in mt5
    assert "evaluate_persisted_account_policy(" in mt5
    assert "connection_id=str(connection_id)" in mt5


def test_agent_council_cannot_enable_copy_trading() -> None:
    source = (ROOT / "core" / "agent_council.py").read_text(encoding="utf-8")
    assert '"enable_copy_trade"' in source
    assert "_FORBIDDEN" in source

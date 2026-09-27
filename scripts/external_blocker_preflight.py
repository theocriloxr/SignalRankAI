"""Fail-closed preflight for SignalRank external activation blockers.

This tool never enables a provider, raises a capacity claim, or activates the
public copy marketplace. It only validates whether the required external
evidence is complete enough to move a traceability item out of
BLOCKED_EXTERNAL for a later, separately authorized change.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REQUIREMENTS = ROOT / "requirements" / "external_activation_requirements.yaml"


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _load_requirements(path: Path = DEFAULT_REQUIREMENTS) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if int(payload.get("schema_version") or 0) != 1:
        raise ValueError("unsupported_external_activation_schema")
    return dict(payload)


def _load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("evidence_must_be_json_object")
    return payload


def _required_true(payload: Mapping[str, Any], names: list[str]) -> list[str]:
    return [name for name in names if payload.get(name) is not True]


def _present_any(environ: Mapping[str, str], names: list[str]) -> bool:
    return any(bool(str(environ.get(name) or "").strip()) for name in names)


def provider_preflight(
    provider: str,
    evidence: Mapping[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
    requirements_path: Path = DEFAULT_REQUIREMENTS,
) -> dict[str, Any]:
    env = dict(os.environ if environ is None else environ)
    reqs = _load_requirements(requirements_path)
    providers = dict(reqs.get("provider_activation") or {})
    key = str(provider or "").strip().lower()
    if key not in providers:
        raise ValueError(f"unknown_provider:{key}")
    spec = dict(providers[key] or {})
    blockers: list[str] = []

    gate_names = [str(spec.get("gate") or "")] + [
        str(name) for name in (spec.get("gate_aliases") or [])
    ]
    gate_names = [name for name in gate_names if name]
    if any(_truthy(env.get(name)) for name in gate_names):
        blockers.append("provider_gate_must_remain_off_during_preflight")

    secret_names = [str(name) for name in (spec.get("required_secret_names") or [])]
    if secret_names and not _present_any(env, secret_names):
        blockers.append("required_provider_secret_missing")

    config_names = [str(name) for name in (spec.get("required_config_names") or [])]
    missing_config = [name for name in config_names if not str(env.get(name) or "").strip()]
    if missing_config:
        blockers.append("required_provider_config_missing:" + ",".join(sorted(missing_config)))

    required_evidence = [str(name) for name in (spec.get("evidence") or [])]
    missing_evidence = _required_true(evidence, required_evidence)
    if missing_evidence:
        blockers.append("provider_external_evidence_missing:" + ",".join(sorted(missing_evidence)))

    if key == "oanda":
        execution_requested = bool(evidence.get("execution_requested"))
        execution_gate_names = ["OANDA_LIVE_EXECUTION_ENABLED"]
        if execution_requested:
            missing_exec = _required_true(
                evidence,
                [str(name) for name in (spec.get("conditional_execution_evidence") or [])],
            )
            if missing_exec:
                blockers.append("oanda_execution_evidence_missing:" + ",".join(sorted(missing_exec)))
        if any(_truthy(env.get(name)) for name in execution_gate_names):
            blockers.append("oanda_live_execution_must_remain_off_during_preflight")

    return {
        "kind": "signalrank_external_provider_preflight",
        "provider": key,
        "status": "ELIGIBLE" if not blockers else "BLOCKED",
        "blockers": blockers,
        "activation_performed": False,
        "claim_allowed": not blockers,
    }


def scale_preflight(
    certification: Mapping[str, Any],
    *,
    requirements_path: Path = DEFAULT_REQUIREMENTS,
) -> dict[str, Any]:
    reqs = _load_requirements(requirements_path)
    spec = dict(reqs.get("scale_activation") or {})
    blockers: list[str] = []

    if certification.get("kind") != spec.get("certification_kind"):
        blockers.append("invalid_scale_certification_kind")
    if certification.get("profile") != spec.get("required_profile"):
        blockers.append("wrong_scale_profile")
    if certification.get("status") != spec.get("required_status"):
        blockers.append("scale_certification_not_pass")
    if certification.get("claim_allowed") is not bool(spec.get("required_claim_allowed")):
        blockers.append("scale_claim_not_allowed")

    concurrency = dict(certification.get("concurrency") or {})
    if int(concurrency.get("actual") or 0) < int(spec.get("concurrent_users") or 0):
        blockers.append("scale_concurrency_below_required")
    load_summary = dict(certification.get("load_summary") or {})
    if int(load_summary.get("configured_total_concurrency") or 0) < int(spec.get("concurrent_users") or 0):
        blockers.append("scale_load_summary_concurrency_below_required")

    return {
        "kind": "signalrank_external_scale_preflight",
        "requirement_id": spec.get("requirement_id"),
        "status": "ELIGIBLE" if not blockers else "BLOCKED",
        "blockers": blockers,
        "activation_performed": False,
        "capacity_claim_allowed": not blockers,
    }


def marketplace_preflight(
    evidence: Mapping[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
    requirements_path: Path = DEFAULT_REQUIREMENTS,
) -> dict[str, Any]:
    env = dict(os.environ if environ is None else environ)
    reqs = _load_requirements(requirements_path)
    spec = dict(reqs.get("marketplace_activation") or {})
    blockers: list[str] = []

    missing_external = _required_true(
        evidence, [str(name) for name in (spec.get("evidence") or [])]
    )
    if missing_external:
        blockers.append("marketplace_external_evidence_missing:" + ",".join(sorted(missing_external)))

    missing_runtime = _required_true(
        evidence, [str(name) for name in (spec.get("runtime_evidence") or [])]
    )
    if missing_runtime:
        blockers.append("marketplace_runtime_evidence_missing:" + ",".join(sorted(missing_runtime)))

    activation_gate = str(spec.get("activation_gate") or "")
    if activation_gate and _truthy(env.get(activation_gate)):
        blockers.append("marketplace_activation_gate_must_remain_off_during_preflight")

    copy_gate = str(spec.get("copy_trade_gate") or "")
    if copy_gate and _truthy(env.get(copy_gate)) and evidence.get("copy_execution_certified") is not True:
        blockers.append("copy_trade_enabled_without_certification")

    return {
        "kind": "signalrank_external_marketplace_preflight",
        "requirement_id": spec.get("requirement_id"),
        "status": "ELIGIBLE" if not blockers else "BLOCKED",
        "blockers": blockers,
        "activation_performed": False,
        "public_marketplace_claim_allowed": not blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    provider = sub.add_parser("provider")
    provider.add_argument("--provider", required=True)
    provider.add_argument("--evidence-json", required=True)

    scale = sub.add_parser("scale")
    scale.add_argument("--certification-json", required=True)

    market = sub.add_parser("marketplace")
    market.add_argument("--evidence-json", required=True)

    args = parser.parse_args()
    if args.command == "provider":
        result = provider_preflight(args.provider, _load_json(args.evidence_json))
    elif args.command == "scale":
        result = scale_preflight(_load_json(args.certification_json))
    else:
        result = marketplace_preflight(_load_json(args.evidence_json))

    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "ELIGIBLE" else 2


if __name__ == "__main__":
    raise SystemExit(main())

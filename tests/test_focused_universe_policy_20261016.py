"""Focused asset shortlist is a staging opt-in, not financial certification."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from core.focused_universe import (
    focused_universe_enabled, load_focused_config, select_focused_assets,
    select_focused_scan_assets,
)


ROOT = Path(__file__).resolve().parents[1]


def test_shortlist_contract_is_identical_to_current_user_scope():
    source = json.loads((ROOT / "docs/release/current_scope_20261016.json").read_text(encoding="utf-8"))
    runtime = load_focused_config()
    assert runtime["asset_classes"] == source["asset_classes"]
    assert runtime["max_active_per_class"] == source["policy"]["max_active_per_class"]
    assert runtime["core_target_per_class"] == source["policy"]["preferred_core_candidates_per_class"]
    assert runtime["mode"] == "staging_opt_in_only"


def test_no_available_instruments_means_no_invented_fallback():
    result = select_focused_assets([])
    assert result.assets == ()
    assert result.offered_count == 0
    assert result.excluded_count == 0
    assert all(n == 0 for n in result.selected_per_class.values())


def test_aliases_and_non_shortlisted_symbols_never_bypass_selection():
    offered = ["USDTIDR", "DOGEIDR", "VIX", "DXY", "BTCUSD", "BTCUSDT", "EURUSD", "US500", "NVDA", "XAUUSD"]
    result = select_focused_assets(offered)
    assert result.assets == ("BTCUSDT", "EURUSD", "US500", "NVDA", "XAUUSD")
    assert result.offered_count == 9  # BTCUSD and BTCUSDT normalize to one instrument
    assert result.excluded_count == 4


def test_listed_but_misclassified_or_unsupported_assets_are_not_promoted():
    result = select_focused_assets(["XPTUSD", "COPPER", "RUSSELL2000", "CHINA50", "SUIUSDT"])
    # Unverified commodity/index mappings must never fall back to US equities.
    assert not {"XPTUSD", "COPPER", "RUSSELL2000", "CHINA50"}.intersection(result.assets)
    assert set(result.assets).issubset({"SUIUSDT"})


def test_every_class_respects_15_cap_even_when_all_candidates_are_offered():
    scope = load_focused_config()
    offered = [s for group in scope["asset_classes"].values() for s in group["core"] + group["optional"]]
    result = select_focused_assets(offered)
    assert result.offered_count <= 75
    assert len(result.assets) <= 75
    assert set(result.selected_per_class) == {"crypto", "forex", "index", "equity", "commodity"}
    assert all(0 <= count <= 15 for count in result.selected_per_class.values())
    assert sum(result.selected_per_class.values()) == len(result.assets)
    assert len(result.assets) == len(set(result.assets))


def test_optional_follows_core_priority():
    result = select_focused_assets(["AVAXUSDT", "BTCUSDT", "ETHUSDT", "DOGEUSDT", "LINKUSDT"])
    assert result.assets[0:2] == ("BTCUSDT", "ETHUSDT")
    assert result.assets[-1] == "AVAXUSDT"


@pytest.mark.parametrize("through_file", [True, False])
@pytest.mark.parametrize("malformation", ["oversized_class", "duplicate_alias", "unknown_class", "remove_mode", "boolean_version", "non_string", "whitespace"])
def test_invalid_runtime_config_fails_closed(tmp_path: Path, malformation: str, through_file: bool):
    config = deepcopy(load_focused_config())
    if malformation == "oversized_class":
        config["asset_classes"]["crypto"]["optional"].append("NOTALLOW")
    elif malformation == "duplicate_alias":
        config["asset_classes"]["crypto"]["optional"][0] = "BTCUSD"
    elif malformation == "unknown_class":
        config["asset_classes"]["other"] = {"core": [], "optional": []}
    elif malformation == "boolean_version":
        config["schema_version"] = True
    elif malformation == "non_string":
        config["asset_classes"]["crypto"]["optional"][0] = 123
    elif malformation == "whitespace":
        config["asset_classes"]["crypto"]["optional"][0] = " BTCUSDT "
    else:
        config.pop("mode")
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError):
        if through_file:
            load_focused_config(path)
        else:
            select_focused_assets(["BTCUSDT"], config=config)


def test_engine_wires_strict_database_read_before_post_merge_selection():
    code = (ROOT / "engine/core.py").read_text(encoding="utf-8")
    marker = 'if _focused_enabled:'
    assert code.count(marker) == 1
    assert code.index("_dedupe_preserve_order(_managed_assets + _saved_assets + _discovered_assets)") < code.index(marker)
    assert code.index(marker) < code.index("_profile_universe_filter_applied = False")
    assert code.index("_focused_enabled = focused_universe_enabled(os.environ)") < code.index("_fetch_database_universe")
    assert "require_analysis_ready=_focused_enabled" in code
    assert code.index("_focused_db_symbols = list(_discovered_assets)") < code.index("_discovered_assets, _class_universe_health = build_class_complete_universe(")
    assert "_focused_db_symbols, universe_source=_universe_source, environment=os.environ" in code


@pytest.mark.parametrize("key", ["RAILWAY_ENVIRONMENT_NAME", "RAILWAY_ENVIRONMENT", "APP_ENV", "ENVIRONMENT"])
@pytest.mark.parametrize("label", ["production", "prod", "preview", "unknown"])
def test_any_production_or_unknown_environment_label_blocks_activation(key, label):
    environment = {"FOCUSED_UNIVERSE_ENABLED": "true", "RAILWAY_ENVIRONMENT_NAME": "staging", "APP_ENV": "test", key: label}
    with pytest.raises(RuntimeError, match="requires_staging_certification"):
        select_focused_scan_assets(["BTCUSDT"], universe_source="database_registry", environment=environment)



def test_missing_environment_and_malformed_enable_flag_fail_closed():
    with pytest.raises(RuntimeError, match="requires_staging_certification"):
        focused_universe_enabled({"FOCUSED_UNIVERSE_ENABLED": "1"})
    with pytest.raises(ValueError, match="invalid_enable_flag"):
        focused_universe_enabled({"FOCUSED_UNIVERSE_ENABLED": "tru", "APP_ENV": "test"})
    assert focused_universe_enabled({"APP_ENV": "production"}) is False
    assert focused_universe_enabled({"FOCUSED_UNIVERSE_ENABLED": "0", "APP_ENV": "production"}) is False


@pytest.mark.parametrize("source", ["legacy_provider_discovery", "legacy_provider_discovery_fallback", "unavailable", ""])
def test_unavailable_database_never_reuses_provider_fallback_symbols(source):
    result = select_focused_scan_assets(["BTCUSDT", "EURUSD"], universe_source=source,
        environment={"FOCUSED_UNIVERSE_ENABLED": "1", "APP_ENV": "test"})
    assert result.assets == ()


def test_staging_scanner_uses_only_supplied_database_candidates():
    result = select_focused_scan_assets(["ETHUSD", "ETHUSDT", "EURUSD", "USDTIDR"],
        universe_source="database_registry",
        environment={"FOCUSED_UNIVERSE_ENABLED": "1", "APP_ENV": "test", "RAILWAY_ENVIRONMENT_NAME": "staging"})
    assert result.assets == ("ETHUSDT", "EURUSD")
    assert "BTCUSDT" not in result.assets
    assert result.excluded_count == 1


def test_disabled_scan_selector_cannot_be_called_to_bypass_activation_guard():
    with pytest.raises(RuntimeError, match="not_enabled"):
        select_focused_scan_assets(["BTCUSDT"], universe_source="database_registry", environment={"APP_ENV": "test"})

"""CX-ASSET-12: ML training uses the same focused-universe membership source.

Every new-entry path already calls ``focused_admission``; the training dataset
did not, so a staging model could learn from instruments the focused platform
will never trade. Disabled leaves data untouched; a production enable flag
fails closed with an empty dataset (the current model is kept).
"""
from __future__ import annotations

import pandas as pd

from ml.train_model import _restrict_to_focused_universe

STAGING = {"FOCUSED_UNIVERSE_ENABLED": "1", "APP_ENV": "staging"}


def _frame():
    df = pd.DataFrame({
        "asset": ["BTCUSDT", "PEPEUSDT", "EURUSD", "NZDCHF", None],
        "target": [1, 0, 1, 0, 1],
    })
    df.attrs["read_status"] = "success"
    return df


def test_disabled_leaves_training_data_untouched():
    df = _frame()
    restricted, focus = _restrict_to_focused_universe(df, {"APP_ENV": "production"})
    assert restricted is df
    assert focus == {"applied": False, "status": "disabled"}


def test_enabled_in_staging_keeps_only_shortlist_members():
    restricted, focus = _restrict_to_focused_universe(_frame(), STAGING)
    assert list(restricted["asset"]) == ["BTCUSDT", "EURUSD"]
    assert focus["status"] == "restricted" and focus["rows_removed"] == 3
    assert focus["instruments_kept"] == ["BTCUSDT", "EURUSD"]
    assert restricted.attrs["read_status"] == "success"


def test_enable_flag_in_production_fails_closed():
    restricted, focus = _restrict_to_focused_universe(
        _frame(), {"FOCUSED_UNIVERSE_ENABLED": "1", "APP_ENV": "production"})
    assert restricted.empty
    assert focus["status"] == "blocked"
    assert focus["reason"] == "focused_universe_requires_staging_certification"


def test_ambiguous_flag_fails_closed():
    restricted, focus = _restrict_to_focused_universe(
        _frame(), {"FOCUSED_UNIVERSE_ENABLED": "maybe", "APP_ENV": "staging"})
    assert restricted.empty and focus["status"] == "blocked"


def test_loader_applies_the_filter_to_the_assembled_dataset():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "ml" / "train_model.py").read_text(encoding="utf-8")
    loader = source[source.index("async def load_training_data("): source.index("def _restrict_to_focused_universe(")]
    assert loader.index("df = pd.DataFrame(data)") < loader.index("_restrict_to_focused_universe(df)")
    assert loader.index("_restrict_to_focused_universe(df)") < loader.index('df.attrs["read_status"] = "success"')

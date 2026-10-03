from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "web" / "userdash" / "templates"


def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(("html", "xml")),
    )


def test_user_dashboard_template_compiles_and_renders_signal_rows_once() -> None:
    template = _environment().get_template("dashboard.html")
    html = template.render(
        tier="VIP",
        show_advanced=True,
        signals=[
            {
                "signal_id": "sig-1",
                "asset": "US30",
                "timeframe": "15m",
                "direction": "SELL",
                "entry": 50686.17,
                "stop_loss": 50877.72,
                "take_profit": "50134.51",
                "score": 85.2,
                "partial_exits": "-",
                "outcome": None,
                "performance": "-",
            }
        ],
    )
    assert html.count("Your Signal Dashboard") == 1
    assert html.count("Tier:") == 1
    assert html.count("sig-1") == 1
    assert "<thead>" in html and "<tbody>" in html
    assert "No active delivered signals" not in html


def test_user_dashboard_empty_state_renders_without_table() -> None:
    template = _environment().get_template("dashboard.html")
    html = template.render(tier="FREE", show_advanced=False, signals=[])
    assert "No active delivered signals are available right now." in html
    assert "<table>" not in html


def test_dashboard_template_keeps_autoescaped_user_values() -> None:
    template = _environment().get_template("dashboard.html")
    html = template.render(
        tier="<script>alert(1)</script>",
        show_advanced=False,
        signals=[],
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html

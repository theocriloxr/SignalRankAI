from pathlib import Path
import re

APP_JS = Path("web/platform_app/app.js").read_text(encoding="utf-8")


def test_multi_element_dom_operations_use_query_selector_all_helper():
    bad = re.findall(r"(?<!\$)\$\('#[^']+'\)\.(?:map|forEach)\(", APP_JS)
    assert bad == []


def test_trading_profile_market_checkboxes_use_multi_selector():
    assert "$$('#tradingProfileForm input[name=\"asset_class\"]').forEach(" in APP_JS
    assert "document.querySelectorAll(\'#tradingProfileForm input[name=\"asset_class\"]:checked\')" in APP_JS

from copy import deepcopy
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from data.connectors import fred_adapter as fred


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv("FRED_ENABLED", "1")
    monkeypatch.setenv("FRED_API_KEY", "owned-test-credential")
    monkeypatch.setenv("FRED_VINTAGE_DATA_ENABLED", "0")


def response(day="2024-02-01", value="2.5"):
    return {"realtime_start": day, "realtime_end": day, "observations": [
        {"date": "2024-01-01", "value": value,
         "realtime_start": day, "realtime_end": day}]}


@pytest.mark.asyncio
async def test_revision_cutoff_is_sent_to_real_adapter_and_later_revisions_do_not_replace_history(monkeypatch):
    requests = []
    async def transport(url, *, params, **kwargs):
        requests.append(deepcopy(params))
        day = params.get("realtime_start")
        return response(day, "2.5" if day == "2024-02-01" else "999")
    monkeypatch.setattr(fred, "async_http_get_json", transport)
    historical = await fred._async_fetch_series("CPIAUCSL", as_of="2024-02-01", end="2025-01-01")
    later = await fred._async_fetch_series("CPIAUCSL", as_of="2024-03-01")
    assert historical[0]["value"] == 2.5 and later[0]["value"] == 999
    assert requests[0]["realtime_start"] == requests[0]["realtime_end"] == "2024-02-01"
    assert requests[0]["observation_end"] == "2024-02-01"
    assert historical[0]["revision_mode"] == "date_vintage"
    assert historical[0]["as_of_date"] == "2024-02-01"
    assert historical[0]["availability_precision"] == "day"
    assert historical[0]["intraday_availability_verified"] is False
    assert datetime.fromisoformat(historical[0]["captured_at"]).tzinfo is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("flag,vintage", [("0", True), ("1", None), ("1", False)])
async def test_vintage_guard_never_silently_fetches_latest_without_explicit_cutoff(monkeypatch, flag, vintage):
    monkeypatch.setenv("FRED_VINTAGE_DATA_ENABLED", flag)
    transport = AsyncMock()
    monkeypatch.setattr(fred, "async_http_get_json", transport)
    assert await fred._async_fetch_series("CPIAUCSL", vintage=vintage) == []
    transport.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("cutoff", ["2024-02-30", "20240201", "2024-02-01T10:00:00Z", "9999-12-31", "", True])
async def test_invalid_or_future_cutoff_does_not_make_a_provider_request(monkeypatch, cutoff):
    transport = AsyncMock()
    monkeypatch.setattr(fred, "async_http_get_json", transport)
    assert await fred._async_fetch_series("CPIAUCSL", as_of=cutoff) == []
    transport.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["response_ignored", "future_observation", "future_vintage",
                                    "expired_vintage", "missing_vintage", "malformed_date", "malformed_row"])
async def test_provider_revision_mismatch_rejects_the_response_instead_of_certifying_it(monkeypatch, mutation):
    data = response()
    row = data["observations"][0]
    if mutation == "response_ignored":
        data["realtime_end"] = "2025-01-01"
    elif mutation == "future_observation":
        row["date"] = "2024-03-01"
    elif mutation == "future_vintage":
        row["realtime_start"] = "2024-02-02"
    elif mutation == "expired_vintage":
        row["realtime_end"] = "2024-01-31"
    elif mutation == "missing_vintage":
        row.pop("realtime_start")
    elif mutation == "malformed_date":
        row["date"] = "2024-02-30"
    else:
        data["observations"].append(None)
    monkeypatch.setattr(fred, "async_http_get_json", AsyncMock(return_value=data))
    assert await fred._async_fetch_series("CPIAUCSL", as_of="2024-02-01") == []


@pytest.mark.asyncio
async def test_latest_context_is_explicitly_unqualified_and_missing_nonfinite_values_are_not_numbers(monkeypatch):
    data = response()
    data["observations"].extend([{"value": value} for value in (".", "NaN", "Infinity", None)])
    transport = AsyncMock(return_value=data)
    monkeypatch.setattr(fred, "async_http_get_json", transport)
    result = await fred._async_fetch_series("CPIAUCSL", start="2024-01-01", end="2024-02-01")
    assert len(result) == 1 and result[0]["revision_mode"] == "latest_revisions"
    assert result[0]["as_of_date"] is None
    assert result[0]["intraday_availability_verified"] is False
    assert "realtime_start" not in transport.call_args.kwargs["params"]


def test_public_sync_entry_point_passes_the_explicit_vintage_contract(monkeypatch):
    seen = {}
    async def transport(url, *, params, **kwargs):
        seen.update(params)
        return response()
    monkeypatch.setattr(fred, "async_http_get_json", transport)
    result = fred.fetch_series("CPIAUCSL", as_of="2024-02-01", vintage=True)
    assert result[0]["value"] == 2.5
    assert seen["realtime_start"] == seen["realtime_end"] == "2024-02-01"


@pytest.mark.asyncio
async def test_empty_unavailable_or_oversized_responses_do_not_fallback_to_latest(monkeypatch):
    for data in (None, {"observations": {}}, response() | {"observations": response()["observations"] * 2}):
        transport = AsyncMock(return_value=data)
        monkeypatch.setattr(fred, "async_http_get_json", transport)
        assert await fred._async_fetch_series("CPIAUCSL", as_of="2024-02-01", limit=1) == []
        assert transport.await_count == 1

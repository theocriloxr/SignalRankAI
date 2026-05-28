from pathlib import Path

import pandas as pd

from scripts.wfo_run import convert_orderbook_file, is_orderbook_frame, normalize_orderbook_frame


def _levels_to_lists(levels):
    return [list(map(float, level)) for level in levels]


def test_normalize_top_of_book_and_convert(tmp_path: Path):
    raw = pd.DataFrame(
        {
            "timestamp": ["2021-01-01T00:00:00Z", "2021-01-01T00:01:00Z"],
            "bidPrice": [99.5, 99.6],
            "bidQty": [1.2, 1.1],
            "askPrice": [100.5, 100.6],
            "askQty": [1.4, 1.3],
        }
    )

    assert is_orderbook_frame(raw, Path("BTCUSDT_5m_orderbook.csv"))

    normalized = normalize_orderbook_frame(raw)
    assert list(normalized.columns) == ["timestamp", "bids", "asks"]
    assert _levels_to_lists(normalized.iloc[0]["bids"]) == [[99.5, 1.2]]
    assert _levels_to_lists(normalized.iloc[0]["asks"]) == [[100.5, 1.4]]

    input_path = tmp_path / "BTCUSDT_5m_orderbook.csv"
    output_path = tmp_path / "out" / "BTCUSDT_5m_orderbook.parquet"
    raw.to_csv(input_path, index=False)
    converted = convert_orderbook_file(input_path, output_path)

    assert converted.exists()
    roundtrip = pd.read_parquet(converted)
    assert list(roundtrip.columns) == ["timestamp", "bids", "asks"]
    assert _levels_to_lists(roundtrip.iloc[0]["bids"]) == [[99.5, 1.2]]

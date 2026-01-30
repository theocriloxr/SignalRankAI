"""Simple demo runner to exercise a strategy with market state."""
from engine.strategies.commodity import CommodityStrategy
from engine.strategies.runner import run_strategy_with_marketstate


def demo_run():
    strat = CommodityStrategy()
    sigs = run_strategy_with_marketstate(strat, "XAUUSD", ["1h", "1d"], include_ml=False)
    print(f"Demo produced {len(sigs)} signals")
    for s in sigs:
        print(s)


if __name__ == "__main__":
    demo_run()

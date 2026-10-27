"""Quick import check for critical modules."""


def run_import_check(verbose: bool = False) -> list[str]:
    errors: list[str] = []

    checks = [
        ("config", lambda: __import__("config").config),
        ("data.fetcher", lambda: __import__("data.fetcher", fromlist=["get_candles"]).get_candles),
        ("data.providers", lambda: __import__("data.providers", fromlist=["fetch_yahoo_candles"]).fetch_yahoo_candles),
        ("db.session", lambda: __import__("db.session", fromlist=["get_session"]).get_session),
        ("db.models", lambda: __import__("db.models", fromlist=["Signal"]).Signal),
        ("engine.risk", lambda: __import__("engine.risk", fromlist=["risk_check"]).risk_check),
        ("engine.scoring", lambda: __import__("engine.scoring", fromlist=["calculate_signal_score"]).calculate_signal_score),
        ("engine.consensus", lambda: __import__("engine.consensus", fromlist=["apply_consensus_filter"]).apply_consensus_filter),
        ("services.signal_orchestrator", lambda: __import__("services.signal_orchestrator", fromlist=["SignalOrchestrator"]).SignalOrchestrator),
        ("signalrank_telegram.bot", lambda: __import__("signalrank_telegram.bot", fromlist=["dispatch_signals_async"]).dispatch_signals_async),
    ]

    for name, importer in checks:
        try:
            importer()
            if verbose:
                print(f"{name}: OK")
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            if verbose:
                print(f"{name}: ERROR: {exc}")

    return errors


def test_critical_imports():
    assert run_import_check() == []


if __name__ == "__main__":
    failures = run_import_check(verbose=True)
    if failures:
        raise SystemExit("\n".join(failures))
    print("ALL IMPORTS OK")

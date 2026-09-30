import asyncio
import os
import sys

def mock_monkeypatch():
    class MockMonkeypatch:
        def setattr(self, target, name, value=None):
            if isinstance(target, str):
                import importlib
                mod_name, attr_name = target.rsplit(".", 1)
                mod = importlib.import_module(mod_name)
                setattr(mod, attr_name, name if value is None else value)
            else:
                setattr(target, name, value)
        def setenv(self, name, value):
            os.environ[name] = value
    return MockMonkeypatch()

def test_behavior():
    monkeypatch = mock_monkeypatch()
    
    from worker.worker import Worker
    import worker.worker as worker_module
    
    called_phases = []
    async def mock_seed(*args, **kwargs):
        called_phases.append("seed")
        return True

    monkeypatch.setattr(worker_module, "is_db_configured", lambda: True)
    
    import db.ecosystem_bootstrap
    monkeypatch.setattr(db.ecosystem_bootstrap, "seed_subscription_catalogue", mock_seed)
    monkeypatch.setattr(db.ecosystem_bootstrap, "seed_ml_governance", mock_seed)
    monkeypatch.setattr(db.ecosystem_bootstrap, "seed_strategy_registry", mock_seed)

    session_calls = []
    class MockSessionContext:
        def __init__(self, **kwargs):
            session_calls.append(kwargs)
        async def __aenter__(self):
            class DummySession:
                async def commit(self): pass
            return DummySession()
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr(worker_module, "get_session", MockSessionContext)

    w = Worker()
    asyncio.run(w._ecosystem_bootstrap_once())

    assert len(called_phases) == 3
    assert len(session_calls) == 3
    print("Test passed!")

if __name__ == "__main__":
    test_behavior()

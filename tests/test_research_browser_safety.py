"""A browser fixture must never create a database on a production target."""
import pytest

from scripts import run_research_browser_drill as drill


@pytest.mark.parametrize("app_env,url", [
    ("production", "postgresql://fixture@127.0.0.1/test_db"),
    ("test", "postgresql://fixture@database.example.test/test_db"),
    ("test", "postgresql://fixture@127.0.0.1/production_db"),
    ("test", "sqlite:///test_db"),
])
def test_drill_rejects_unsafe_targets_before_any_database_connection(monkeypatch, tmp_path, app_env, url):
    def forbidden_connect(*args, **kwargs):
        pytest.fail("unsafe drill reached database connection")
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(drill.psycopg2, "connect", forbidden_connect)
    monkeypatch.setattr(drill.sys, "argv", ["drill", "--output-dir", str(tmp_path)])
    with pytest.raises(RuntimeError, match="loopback test database"):
        drill.main()

import pytest
from db.migration_environment import load_migration_environment


@pytest.mark.parametrize("scope", ["explicit_off", "production", "railway"])
def test_hermetic_or_production_migrations_do_not_load_local_files(tmp_path, monkeypatch, scope):
    monkeypatch.delenv("SIGNALRANK_ALLOW_DOTENV", raising=False)
    monkeypatch.setenv("APP_ENV", "test")
    for name in ("RAILWAY_PROJECT_ID", "RAILWAY_ENVIRONMENT_ID", "RAILWAY_SERVICE_ID"):
        monkeypatch.delenv(name, raising=False)
    if scope == "explicit_off":
        monkeypatch.setenv("SIGNALRANK_ALLOW_DOTENV", "0")
    elif scope == "production":
        monkeypatch.setenv("APP_ENV", "production")
    else:
        monkeypatch.setenv("RAILWAY_PROJECT_ID", "fixture-project")
    def forbidden(*args, **kwargs):
        pytest.fail("dotenv must not be read")
    monkeypatch.setattr("dotenv.load_dotenv", forbidden)
    load_migration_environment(tmp_path)


def test_local_file_cannot_replace_explicit_migration_destination(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNALRANK_ALLOW_DOTENV", "1")
    monkeypatch.setenv("DATABASE_MIGRATION_URL", "postgresql://localhost/explicit_test")
    (tmp_path / ".env").write_text("DATABASE_MIGRATION_URL=postgresql://localhost/wrong_test\n")
    (tmp_path / ".env.local").write_text("DATABASE_MIGRATION_URL=postgresql://localhost/another_wrong_test\n")
    load_migration_environment(tmp_path)
    assert __import__("os").environ["DATABASE_MIGRATION_URL"] == "postgresql://localhost/explicit_test"


def test_invalid_migration_policy_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNALRANK_ALLOW_DOTENV", "sometimes")
    with pytest.raises(RuntimeError, match="invalid_migration_dotenv_policy"):
        load_migration_environment(tmp_path)

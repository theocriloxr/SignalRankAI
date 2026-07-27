from pathlib import Path


def test_alembic_prefers_direct_migration_url():
    source = Path('db/migrations/env.py').read_text(encoding='utf-8')
    assert 'DATABASE_MIGRATION_URL' in source
    assert 'DATABASE_DIRECT_URL' in source
    assert source.index('DATABASE_MIGRATION_URL') < source.index('app_config.DATABASE_URL')

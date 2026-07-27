import json
from pathlib import Path


def test_railway_activates_only_when_dependencies_ready():
    data = json.loads(Path('railway.json').read_text(encoding='utf-8'))
    assert data['deploy']['healthcheckPath'] == '/readyz'


def test_runtime_schema_bootstrap_is_opt_in():
    source = Path('db/auto_ops.py').read_text(encoding='utf-8')
    assert 'STARTUP_SCHEMA_BOOTSTRAP", False' in source

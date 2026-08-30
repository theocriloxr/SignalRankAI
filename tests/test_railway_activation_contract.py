import json
from pathlib import Path


def test_railway_uses_neutral_multiservice_config_and_frontdoor_readiness():
    data = json.loads(Path('railway.json').read_text(encoding='utf-8'))
    assert data['deploy']['startCommand'] == 'bash start.sh'
    assert 'healthcheckPath' not in data['deploy']
    split = Path('split_signalrank_railway.ps1').read_text(encoding='utf-8')
    assert 'Set-ServiceConfig -Service $SourceService -Path "healthcheckPath" -Value "/readyz"' in split


def test_runtime_schema_bootstrap_is_opt_in():
    source = Path('db/auto_ops.py').read_text(encoding='utf-8')
    assert 'STARTUP_SCHEMA_BOOTSTRAP", False' in source

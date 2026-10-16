from types import SimpleNamespace

import pytest

from engine import ml as engine_ml
from ml.model_registry import compute_feature_schema_hash
from ml.schema_version import FEATURE_COLUMNS_V3, FEATURE_COLUMNS_V4, get_feature_columns


@pytest.mark.parametrize('version,columns', [(3, FEATURE_COLUMNS_V3), (4, FEATURE_COLUMNS_V4)])
@pytest.mark.parametrize('candidate', [False, True])
def test_loader_honors_artifact_contract_without_promoting_challenger(monkeypatch, tmp_path, version, columns, candidate):
    cache=engine_ml._SHADOW_CACHE if candidate else engine_ml._MODEL_CACHE
    previous=dict(cache)
    path=tmp_path/'model.json'
    path.write_text('{}')
    monkeypatch.setattr(engine_ml, '_model_path', lambda:path)
    monkeypatch.setenv('ML_CANDIDATE_MODEL_PATH',str(path))
    booster=SimpleNamespace(set_param=lambda *args:None)
    metadata={'version':'approved-test-model','schema_version':version,
              'feature_schema_hash_sha256':compute_feature_schema_hash(columns)}
    monkeypatch.setattr(engine_ml,'load_model_with_metadata',lambda *args:(booster,list(columns),metadata,None))
    try:
        cache.update(loaded=False,booster=None)
        if candidate:
            engine_ml._load_shadow_model(sync_durable=False)
        else:
            engine_ml._load_model(sync_durable=False)
        assert cache['booster'] is booster
        assert cache['feature_cols']==columns
        assert cache['error'] is None
        assert get_feature_columns()==FEATURE_COLUMNS_V4
    finally:
        cache.clear()
        cache.update(previous)


@pytest.mark.parametrize('version,columns', [(3,FEATURE_COLUMNS_V4),(4,FEATURE_COLUMNS_V3),(3,list(reversed(FEATURE_COLUMNS_V3))),(99,FEATURE_COLUMNS_V4)])
def test_primary_rejects_misdeclared_reordered_or_unknown_contract(monkeypatch, tmp_path, version, columns):
    previous=dict(engine_ml._MODEL_CACHE)
    path=tmp_path/'model.json'
    path.write_text('{}')
    monkeypatch.setattr(engine_ml,'_model_path',lambda:path)
    metadata={'schema_version':version,'feature_schema_hash_sha256':compute_feature_schema_hash(columns)}
    monkeypatch.setattr(engine_ml,'load_model_with_metadata',lambda *args:(SimpleNamespace(set_param=lambda *args:None),columns,metadata,None))
    try:
        engine_ml._MODEL_CACHE.update(loaded=False,booster=None)
        engine_ml._load_model(sync_durable=False)
        assert engine_ml._MODEL_CACHE['booster'] is None
        assert engine_ml._MODEL_CACHE['error'] is not None
    finally:
        engine_ml._MODEL_CACHE.clear()
        engine_ml._MODEL_CACHE.update(previous)

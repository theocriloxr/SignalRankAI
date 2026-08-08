from pathlib import Path


def test_subscription_price_bootstrap_uses_typed_bindparams_for_asyncpg():
    source = Path('db/ecosystem_bootstrap.py').read_text(encoding='utf-8')
    assert 'bindparam("product_id", type_=String(64))' in source
    assert 'bindparam("price_kobo", type_=BigInteger())' in source
    assert 'ON CONFLICT (product_id,currency,effective_from) DO UPDATE SET' in source
    assert 'effective_until=NULL' in source
    # Regression guard for asyncpg AmbiguousParameterError caused by the old form.
    assert "SELECT :product_id,'NGN',:price_kobo" not in source


def test_catalogue_persists_every_canonical_feature_entitlement():
    source = Path('db/ecosystem_bootstrap.py').read_text(encoding='utf-8')
    assert 'base[f"feature.{feature_name}"] = (True, None, None, 20)' in source
    assert 'feature_entitlements' in source
    assert 'control_entitlements' in source
    assert 'verify_ecosystem_bootstrap' in source

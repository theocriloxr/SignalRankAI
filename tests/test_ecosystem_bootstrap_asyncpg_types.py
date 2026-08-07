from pathlib import Path


def test_subscription_price_bootstrap_casts_reused_product_parameter_for_asyncpg():
    source = Path('db/ecosystem_bootstrap.py').read_text(encoding='utf-8')
    assert 'CAST(:product_id AS VARCHAR(64))' in source
    assert 'CAST(:price_kobo AS BIGINT)' in source
    assert "CAST('NGN' AS VARCHAR(8))" in source
    # Regression guard for asyncpg AmbiguousParameterError caused by the old form.
    assert "SELECT :product_id,'NGN',:price_kobo" not in source
    assert 'WHERE product_id=:product_id' not in source

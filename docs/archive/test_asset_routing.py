"""
Test script for Asset Routing Fix
Run this to verify the fix is working correctly.
"""
import sys
sys.path.insert(0, '.')

def test_asset_type_detection():
    """Test that asset types are correctly detected."""
    from data.fetcher import get_asset_type, is_crypto, is_stock, is_commodity, is_fx
    
    test_cases = [
        # (symbol, expected_type)
        ("BTCUSDT", "crypto"),
        ("ETHUSDT", "crypto"),
        ("MA", "stock"),  # Mastercard
        ("AAPL", "stock"),
        ("WTI", "commodity"),  # Crude Oil
        ("XAUUSD", "commodity"),  # Gold
        ("XAGUSD", "commodity"),  # Silver
        ("EURUSD", "fx"),
    ]
    
    print("\n=== Test Asset Type Detection ===")
    passed = 0
    failed = 0
    
    for symbol, expected in test_cases:
        actual = get_asset_type(symbol)
        status = "✅" if actual == expected else "❌"
        print(f"  {status} {symbol}: expected={expected}, actual={actual}")
        if actual == expected:
            passed += 1
        else:
            failed += 1
    
    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


def test_ticker_namespacing():
    """Test ticker namespacing functions."""
    from data.fetcher import parse_symbol, normalize_symbol
    
    test_cases = [
        # (input, expected_namespace, expected_raw)
        ("EQUITY:MA", "EQUITY", "MA"),
        ("COMMODITY:WTI", "COMMODITY", "WTI"),
        ("CRYPTO:BTCUSDT", "CRYPTO", "BTCUSDT"),
        ("FX:EURUSD", "FX", "EURUSD"),
        ("MA", None, "MA"),
        ("WTI", None, "WTI"),
    ]
    
    print("\n=== Test Ticker Namespacing ===")
    passed = 0
    failed = 0
    
    for symbol, expected_ns, expected_raw in test_cases:
        ns, raw = parse_symbol(symbol)
        status = "✅" if ns == expected_ns else "❌"
        print(f"  {status} parse_symbol({symbol}): ns={ns}, raw={raw}")
        if ns == expected_ns and raw == expected_raw:
            passed += 1
        else:
            failed += 1
    
    # Test normalize_symbol
    norm_cases = [
        ("MA", "EQUITY:MA"),
        ("WTI", "COMMODITY:WTI"),
        ("BTCUSDT", "CRYPTO:BTCUSDT"),
        ("EURUSD", "FX:EURUSD"),
    ]
    
    for symbol, expected in norm_cases:
        actual = normalize_symbol(symbol)
        status = "✅" if actual == expected else "❌"
        print(f"  {status} normalize_symbol({symbol}): {actual}")
        if actual == expected:
            passed += 1
        else:
            failed += 1
    
    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


def test_provider_routing():
    """Test that providers are correctly routed."""
    from data.connector_registry import get_providers_for_asset
    
    print("\n=== Test Provider Routing ===")
    
    # Crypto should use crypto providers
    crypto_providers = get_providers_for_asset("crypto")
    crypto_provider_names = [name for name, _ in crypto_providers]
    print(f"  Crypto providers: {crypto_provider_names}")
    
    # Stock should use stock providers
    stock_providers = get_providers_for_asset("stock")
    stock_provider_names = [name for name, _ in stock_providers]
    print(f"  Stock providers: {stock_provider_names}")
    
    # Commodity should use commodity providers (NOT crypto!)
    commodity_providers = get_providers_for_asset("commodity")
    commodity_provider_names = [name for name, _ in commodity_providers]
    print(f"  Commodity providers: {commodity_provider_names}")
    
    # FX should use FX providers
    fx_providers = get_providers_for_asset("fx")
    fx_provider_names = [name for name, _ in fx_providers]
    print(f"  FX providers: {fx_provider_names}")
    
    # Verify no crypto providers in commodity list
    crypto_in_commodity = any("binance" in n or "bybit" in n or "cryptocompare" in n for n in commodity_provider_names)
    if crypto_in_commodity:
        print("\n  ❌ ERROR: Crypto providers found in commodity list!")
        return False
    
    print("\n  ✅ Provider routing is correct!")
    return True


def test_market_hours():
    """Test market hours checking."""
    from data.fetcher import is_market_open, market_closed_reason, get_asset_type
    
    print("\n=== Test Market Hours ===")
    
    # Crypto should always be open
    crypto_open = is_market_open("BTCUSDT")
    print(f"  is_market_open(BTCUSDT): {crypto_open}")
    if not crypto_open:
        print("  ❌ ERROR: Crypto should always be open!")
        return False
    
    # Test stock market hours
    asset_type = get_asset_type("AAPL")
    closed_reason = market_closed_reason("AAPL")
    print(f"  market_closed_reason(AAPL): {closed_reason}")
    
    print("\n  ✅ Market hours check working!")
    return True


def test_strict_provider():
    """Test strict provider routing function."""
    from data.fetcher import get_strict_provider_for_asset, get_asset_type
    
    print("\n=== Test Strict Provider Functions ===")
    
    test_cases = [
        ("BTCUSDT", "crypto"),
        ("MA", "stock"),
        ("WTI", "commodity"),
        ("EURUSD", "fx"),
    ]
    
    passed = 0
    failed = 0
    
    for symbol, expected_type in test_cases:
        asset_type, providers = get_strict_provider_for_asset(symbol)
        status = "✅" if asset_type == expected_type else "❌"
        print(f"  {status} {symbol}: type={asset_type}, providers={providers[:2]}...")
        if asset_type == expected_type:
            passed += 1
        else:
            failed += 1
    
    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


def main():
    """Run all tests."""
    print("=" * 60)
    print("Asset Routing Fix - Test Suite")
    print("=" * 60)
    
    results = []
    
    results.append(("Asset Type Detection", test_asset_type_detection()))
    results.append(("Ticker Namespacing", test_ticker_namespacing()))
    results.append(("Provider Routing", test_provider_routing()))
    results.append(("Market Hours", test_market_hours()))
    results.append(("Strict Provider", test_strict_provider()))
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\n✅ All tests passed! The fix is working correctly.")
        return 0
    else:
        print("\n❌ Some tests failed. Please review the implementation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

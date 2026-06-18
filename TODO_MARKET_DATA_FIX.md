# TODO: Market Data Fix Implementation

## Priority 1: CRITICAL - Data Quality Gates
- [x] Read engine/core.py to understand current flow
- [x] Create MARKET_DATA_FIX_PLAN.md
- [ ] Add validate_data_quality() function in engine/core.py
- [ ] Call validate_data_quality() before strategy execution
- [ ] Add quality rejection logging

## Priority 2: CRITICAL - Verify Provider Fallback
- [ ] Test Bybit connector works
- [ ] Verify crypto chain: Bybit -> KuCoin -> CoinGecko -> Yahoo
- [ ] Verify commodity chain: TwelveData -> Yahoo -> Stooq
- [ ] Add explicit logging for provider fallback

## Priority 3: HIGH - Market Session Quality
- [ ] Add is_tradeable_now() to data/market_hours.py
- [ ] Check overnight liquidity for XAUUSD, commodities
- [ ] Add poor liquidity rejection logging

## Priority 4: MEDIUM - Asset Ranking
- [ ] Add rank_assets_for_analysis() function
- [ ] Limit to top 10 on Railway
- [ ] Score by liquidity + volatility + trend

## Testing Checklist
- [ ] generated_signals > 0 in logs
- [ ] provider fallback shown in logs
- [ ] data_quality_rejected count tracked
- [ ] No more "No timeframe data for X" errors

## Implementation Updates
- [2025-01-XX] Initial plan created
- [2025-01-XX] fetcher_router.py verified - already has good provider chains
- [2025-01-XX] engine/core.py has extensive stale data checking but needs quality gates

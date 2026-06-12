# TODO: Multi-Provider Data Pipeline Fix (STARVATION_FIX_V5)

## Status: IN PROGRESS

## Task List

- [ ] 1. Create KuCoin adapter (no API key required for crypto)
- [ ] 2. Create Tiingo adapter (API key: TIINGO_API_KEY)
- [ ] 3. Create FMP adapter (Financial Modeling Prep - API key: FMP_API_KEY)  
- [ ] 4. Update fetcher_router.py with new fallback chains
- [ ] 5. Test imports and verify adapter registration

## PLAN APPROVED BY: User

## Implementation Notes

### KuCoin Adapter
- Provider: https://api.kucoin.com/api/v1/market/candles
- Symbol format: BTC-USDT (replace "/" with "-")
- Timeframe: 1hour, 4hour, 1day
- NO API KEY REQUIRED

### Tiingo Adapter  
- Provider: https://api.tiingo.com
- API Key env: TIINGO_API_KEY
- Endpoints for crypto/stocks/forex
- Free tier: 500 requests/hour

### FMP Adapter
- Provider: https://financialmodelingprep.com
- API Key env: FMP_API_KEY
- Free tier: 250 requests/day
- Best for stocks

### Router Update
```python
FALLBACK_ROUTING = {
    "crypto": ["binance", "kucoin", "cryptocompare", "tiingo", "yfinance"],
    "stocks": ["tiingo", "twelvedata", "fmp", "yfinance"],
    "fx": ["twelvedata", "tiingo", "yfinance"],
    "commodities": ["twelvedata", "tiingo", "yfinance"]
}

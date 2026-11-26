# Real-time prices for every asset class (26 Nov 2026)

A signal is only sent after a live quote proves the price is fresh: at most 10 s old for crypto,
15 s for FX/metals/commodities, 30 s for indices/stocks (`data/provider_types.FinalQuotePolicy`).

| Class | Free sources and their real age | Passes? |
|---|---|---|
| Crypto | Coinbase/OKX/Binance/Bybit bid-ask, seconds | yes |
| FX crosses | Yahoo tick time via yfinance, 2-3 s (EURUSD sometimes 30 s) | yes, mostly |
| Indices (cash) | Yahoo, delayed 15 min by the exchanges | no |
| Gold, silver, oil, US index futures | Yahoo CME futures, delayed 10 min | no |
| US stocks | FMP in market hours | yes in hours |

**OANDA free practice API** fixes indices, metals and oil: real-time CFD prices with tick times for
GER40 (DE30_EUR), UK100, US30, US500, NAS100, JP225, HK50 (HK33_HKD), EU50, FRA40, AUS200, NTH25,
SWI20, WTI, Brent, natural gas, XAU, XAG, XPT and all FX pairs. The code maps every one
(`services/asset_mapper._OANDA_CFD`) and uses OANDA for candles and for the final-send quote.

Setup (owner, on the server; the token never goes through git or chat):

1. Open a free OANDA demo (practice) account and create a personal access token
   (My Account -> Manage API Access). Note the v20 account id (e.g. 101-004-1234567-001).
2. On the server:
   `sudo sr env-set OANDA_API_KEY=<token> backend`
   `sudo sr env-set OANDA_ACCOUNT_ID=<account id> backend`
   `sudo sr env-set OANDA_ENABLED=1 backend`
3. Then put OANDA first for these classes (no secret in it):
   `INDEX_MARKET_DATA_PROVIDERS=oanda,yfinance,twelvedata,polygon`,
   `INDEX_PREFERRED_PROVIDER=oanda`, `COMMODITY_PREFERRED_PROVIDER=oanda`, `FX_PREFERRED_PROVIDER=oanda`.

MetaApi (broker-native FundedNext prices) is also supported: set `META_API_MARKET_DATA_ACCOUNT_ID`
once a MetaApi account exists for the FundedNext MT5 login. TradingView is not used: it has no
public data API and the unofficial websocket scrapers breach its terms.

The public track record counts only signals that actually reached someone (`sent_ok` or a
confirmed delivery); until 26 Nov the always-set `delivered_at` default let blocked signals in.

# BLOCKED_EXTERNAL_REQUIREMENTS — SignalRankAI

Everything below is fully implemented locally (adapter/capability declaration,
configuration, sandbox harness or contract) but **cannot be certified from
this repository** because it requires an external credential, paid feed,
broker approval, cloud resource or legal/licensing decision. Features listed
here are disabled by default and must NOT be advertised as certified.

| # | Capability | External dependency | Local state | Required to certify |
|---|---|---|---|---|
| B-01 | Paystack live checkout | live `sk_live_`/`pk_live_` key pair + real test charge | complete (test-ready) | staging test txn + signed webhook runtime evidence |
| B-02 | Staging/prod Telegram webhooks | staging bot token + public domain per env | complete | webhook ownership diagnostics in deployed logs |
| B-03 | Live broker execution (Bybit/MT5/OANDA/IBKR/Alpaca/Tradier) | credentials, broker approval, jurisdiction/KYC | declarations + fail-closed gates | testnet/sandbox certification per venue |
| B-04 | Hyperliquid + DEX adapters | wallet/key isolation, testnet funds | DECLARED | testnet certification, key-handling audit |
| B-05 | MetaAPI account-bound live quotes | MetaAPI account + token | adapters present | per-account runtime evidence |
| B-06 | Twelve Data / Polygon / Finnhub / Tiingo etc. | paid subscription keys | typed adapters + failure classification | quota-based runtime evidence |
| B-07 | Options chains / greeks | licensed options feed | DECLARED | licensing decision |
| B-08 | On-chain metrics | reliable data provider keys | DECLARED | licensing + source QA |
| B-09 | 100k-user load certification | representative Railway infra + budget | load-profile plan needed | actual load/soak/chaos runs |
| B-10 | Web/mobile product | (frontend not present) | roadmap + contracts | frontend build + auth review |
| B-11 | Copy trading | legal/suitability decision | roadmap, DISABLED | legal + execution certification |
| B-12 | Strategy marketplace | legal/fraud controls | roadmap, DISABLED | publisher verification system |
| B-13 | Backup restore drills | object storage + production access | documented | executed restore test |
| B-14 | SBOM / SAST / container scans | CI/registry access | documented requirements | executed pipeline |

Any future commit that claims one of these is certified without the listed
runtime evidence is a certification violation.

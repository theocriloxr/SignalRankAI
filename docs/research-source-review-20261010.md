# Independent review of the supplied research source

The owner supplied the previously inaccessible document content on 2026-10-10.
The complete supplied text is preserved at
`docs/specs/20261010/research-source-supplied.md`, SHA-256
`e2eb70cc274b9706def06d1b4565860c672763784cf5c72381186da12ebde333`.
This completes review of the supplied content. Its authorship and Google Docs
revision identity have not been authenticated. Source line numbers below refer
to that preserved file, including its escaped Markdown code. Its examples are
illustrations, not empirical evidence of an edge or an approved deployment.

## Concept extraction and repository disposition

| Source concept | Disposition | Repository implementation and judgment |
|---|---|---|
| Economic mechanism, counterparty and persistence hypothesis | ALREADY_PRESENT | Research hypothesis specifications record mechanism status. The adaptive proxy remains `mechanism_unproven`; a persuasive explanation cannot establish persistence. |
| Separate hypothesis, code, critic, statistician and risk roles | IMPROVED | Deterministic integrity, statistics, sizing and promotion gates remain separate from AI assistance. Independent prompts alone are not independent empirical validation. Full AI provider/model/prompt provenance remains incomplete. |
| Vectorized backtesting instead of repeated engine rewrites | REJECTED_WITH_REASON | Retain and repair the existing engines. Event replay is needed for stops, partial fills and observation availability; prohibiting loops is not a correctness requirement. No disconnected toy engine was added. |
| Shift signals before exposure | IMPROVED | `engine/backtest.py`, `engine/wfo.py` and `engine/backtest_execution.py` use whole-bar availability and decision timestamps. Source line 107 contains `position = signal.shift(1).fillna(0).clip(`. A one-row shift cannot prove feature, publication or fill availability. |
| Capped leverage and initial capital | IMPROVED | Existing bounded spot-unit risk advice validates finite equity and preserves hard stops. A leverage cap alone cannot enforce margin, venue units, shared equity or an account loss budget. Those qualification gaps remain explicit. |
| Fees, slippage and turnover | IMPROVED | Conservative replay includes entry and stop-exit costs, preserves gaps and exposes modeled/observed risk-budget breaches. Source line 81 calls the fee round-trip while line 123 charges it on turnover: that convention must be resolved per venue. Terminal liquidation, financing and instrument costs remain unqualified. |
| Log-return portfolio accounting | REJECTED_WITH_REASON | Multiplying an arbitrary short/leveraged position by the asset log return and exponentiating the sum is not general self-financing portfolio accounting. For simple asset return r and exposure w, portfolio gross return is w*r, and its log return is log(1+w*r), when solvent. These are not w*log(1+r). Retain explicit fill/P&L accounting. |
| Sharpe, volatility and annual return | IMPROVED | `engine/adaptive/statistics.py` requires explicit observation frequency for equally spaced excess returns. Irregular trade R is not annualized. Mean log return times periods/year is a log growth rate, not the reported compounded annual percentage return. Risk-free return and serial dependence need explicit treatment. |
| Initial-peak drawdown and Calmar | IMPROVED | Trade-R drawdown includes the initial zero peak; initial losses cannot disappear from the path. A Calmar numerator and denominator must share compatible portfolio/time units. No Calmar is fabricated from irregular R. |
| Drawdown duration | IMPROVED | Duration is recorded in observations and open drawdown is retained. Source line 205 names observation counts `longest_dd_days`; this is only valid with a verified daily calendar. |
| Sharpe above 2 or 3 proves leakage | REJECTED_WITH_REASON | Source line 213 makes a categorical claim. High Sharpe warrants investigation but cannot prove a particular defect. Sample size, multiple testing, dependence, costs and instrument structure matter. |
| Eight-check adversarial audit with quoted evidence | IMPROVED | `engine/adaptive/integrity.py` distinguishes demonstrated PASS from UNVERIFIED. Requiring only PRESENT/ABSENT would falsely certify unspecified universe, fills, feature history or calendar conventions. See the audit table below. |
| Delisted instruments and survivorship | DEFERRED_WITH_REASON | Point-in-time universe membership, delistings and historical revisions still require actual datasets and qualification. No current asset list can prove their historical absence. |
| Repainting, pivots and unavailable indicators | IMPROVED | Closed-bar and future-price mutation tests exist. A complete component-by-component pivot/repaint and feature-vintage audit remains unfinished. |
| Trial counting, including rejected variants | ALREADY_PRESENT | Append-only `research_hypotheses`, `research_experiments` and terminal results retain retries/lineage and failed trials. Pre-ledger historical search coverage remains unverified. |
| Deflated Sharpe Ratio | IMPROVED | The existing implementation uses unannualized Sharpe, cross-trial Sharpe variance, observed moments, raw trial counts and explicit frequency. Source lines 271–291 mix annualized input with an unscaled expected maximum; N=1 also produces an infinite quantile. Do not copy it. Dependence and historical trial completeness remain qualifications. |
| Significance threshold as trade authorization | REJECTED_WITH_REASON | A statistical threshold is one gate; it cannot authorize an account, broker order, live-money rollout or a profitable-strategy claim. |
| Rolling train/test walk-forward optimization | IMPROVED | Preserve the existing purged, chronological adaptive WFO and availability-bounded legacy WFO. Source `iloc` windows are observations despite names ending in days. Repeated test reuse and fold-boundary costs require governance. |
| Worst-fold reporting instead of averages | ALREADY_PRESENT | Promotion policy requires fold counts, positive-fold proportion and worst-fold expectancy. Short/empty folds remain explicit; no metric is inferred from an error object. |
| Walk-forward cannot get lucky | REJECTED_WITH_REASON | WFO can still suffer test reuse, researcher selection and regime luck. Immutable experiment records, independent evidence, dependence-aware inference and forward observation remain necessary. |
| Rich regime breakdown | IMPROVED | Retain existing regimes; do not reduce them to a 200-period moving-average split. Supported/disabled regime policies, transition coverage and regime-specific qualifications remain unfinished. |
| Position size from capital, stop and a notional cap | IMPROVED | Existing shared bounded advisers validate side, geometry, costs, finite values, zero budgets and floating-point bounds. Source raw absolute distance omits these. Broker contract/lot rounding, margin, concurrent capital and funded-account rules remain unqualified. |
| Loss-streak survival and trade-frequency dependence | IMPROVED | Block-bootstrap survival diagnostics exist. The claimed annual frequency of a losing streak cannot be accepted without the trade count and dependence model. Full instrument/portfolio survival qualification remains unfinished. |
| Post-deployment checks independent of optimization | ALREADY_PRESENT | The analytics health loop runs when research is disabled/paused, shares lifecycle locks and issues short leases. Outages expire approvals; suspensions require revalidation. |
| Persistent approved baseline and decay limits | IMPLEMENTED | Migration `0051_strategy_health_baselines` adds immutable delivery-baseline approvals and health events. The owner chooses every limit before runtime promotion. Forward decisions are separated from baseline-era decisions; fingerprints bind profile configuration and version. |
| 30 observations, 365 periods, 50% Sharpe decay and 1.5x drawdown | REJECTED_WITH_REASON | No universal constants are copied. Delivery monitoring does not calculate a daily Sharpe from trade R. Sample requirements and decay/absolute limits are explicit per approved profile, with configuration validation. |
| Calibration drift | IMPROVED | Canonical validated probabilities are compared per qualified calibration version. Required missing/small-version coverage remains unavailable and blocks cache approval; heuristic confidence is excluded. |
| Automatic disablement on degradation | IMPROVED | Approved-limit breaches suspend the adaptive profile and invalidate its cache in the existing locked transaction. Immutable health evidence records reasons. Approval does not reactivate or authorize execution. Wider execution/portfolio kill-condition orchestration remains unfinished. |
| High hypothesis throughput and rejection rates prove discipline | REJECTED_WITH_REASON | The source supplies no evidence for those claims. Throughput and rejecting 199/200 hypotheses cannot certify scientific validity or profitability. |

## Eight-check assessment of the illustrative source

These classifications apply to what the supplied example demonstrates, not to
an unseen strategy, dataset or live system.

| Check | Assessment | Evidence and limit |
|---|---|---|
| Unshifted signal exposure | ABSENT in the shown expression | Line 107 shifts the signal. Timestamp/feature/fill look-ahead is still UNVERIFIED. |
| Survivorship | UNVERIFIED | No historical universe or delisting manifest is supplied. |
| Indicator repainting | UNVERIFIED | The signal and indicator implementation is not supplied. |
| Fee/slippage omission | ABSENT as arithmetic terms | Line 123 includes both. Venue calibration, charging convention and complete cost coverage are UNVERIFIED. |
| Unavailable-price fills | UNVERIFIED | There is no quote/order replay or availability contract. |
| Whole-dataset parameter fitting | UNVERIFIED | The optimizer and signal function are unspecified; a caller may still leak the test set. |
| Bull/bear sample coverage | UNVERIFIED | The supplied text has no actual historical sample. |
| Timezone and bar-close alignment | UNVERIFIED | The example does not validate either. |

## Independent mathematical cross-check

Bailey and López de Prado's original [DSR paper](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)
uses selection information including the variance of Sharpe estimates, sample
length and distribution moments. That supports retaining the repository's
scaled implementation rather than the source's illustrative function. Lo's
[original Sharpe-ratio paper](https://rpc.cfainstitute.org/research/financial-analysts-journal/2002/the-statistics-of-sharpe-ratios)
examines dependence and time aggregation; frequency labels alone cannot justify
square-root annualization. The portfolio-accounting and initial-peak findings
above follow directly from the shown equations, rather than asserting an
empirical trading result.

## Completion boundary

The supplied-content review is complete. Research directive implementation is
still in progress. Delivery baselines cannot stand in for broker/paper fills,
uniform portfolio time returns, instrument costs/capacity, portfolio interaction,
point-in-time universe evidence, full regime policies or validated strategy edge.
No production or account approval is granted by this review.

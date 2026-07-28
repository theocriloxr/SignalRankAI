# Adaptive Strategy Intelligence Data Dictionary v1.1.0

## `adaptive_strategy_specs`
Versioned machine-readable strategy specifications. Key fields: `strategy_id`, `version`, `family`, `creation_source`, `state`, `spec`, `dataset_version`, `feature_version`, approval and suspension data.

## `adaptive_asset_profiles`
Per-asset champion/challenger profiles. Key fields: `profile_id`, `asset`, `asset_class`, `version`, lifecycle `state`, `is_current`, family/regime weights, preferred timeframes/sessions, confidence and reward/risk floors, bounded multiplier limits, sample size, sufficiency, parent/rollback profile IDs, and auditable metadata.

## `adaptive_signal_evidence`
Structured component evidence attached to a persisted signal. It stores component/version, family, direction, setup type, confidence, raw score, quality classification, profile version, regime, data-quality evidence, conflicts, and a duplicate fingerprint.

## `adaptive_signal_sequences`
References the exact candle sequence used at decision time. It stores a stable sequence hash, timeframe, count, start/end times, provider, evidence stage, and compact summary. Full candles remain in `market_candles`.

## `adaptive_dataset_versions`
Immutable dataset manifests. It records the content hash, row count, chronological boundaries, evidence categories, assets, sequence coverage and complete manifest.

## `adaptive_feature_versions`
Immutable feature-contract versions. It records component versions and the structured evidence schema.

## `adaptive_walk_forward_runs`
Chronological validation evidence for a profile candidate. It records dataset/feature versions, configuration, fold boundaries, metrics and status.

## `adaptive_optimisation_runs`
Top-level analytics run evidence, including mode, dataset/feature versions, configuration, summary, status and failure reason.

## `adaptive_promotion_events`
Append-only owner governance trail. It records from/to state, decision, reasons, metrics, actor Telegram ID and a deterministic idempotency key.

## `adaptive_drift_events`
Runtime degradation records. It stores asset/profile, drift type, severity, observed metrics, resolution and timestamps.

## Canonical existing tables reused

- `market_candles`: canonical time-series storage.
- `signals`: generated/stored signal truth.
- `signal_deliveries`: Telegram-confirmed delivery truth.
- `outcomes`: lifecycle outcome and R-multiple truth.
- `trades`: execution evidence where a broker action occurred.

## Evidence categories

`generated`, `stored`, `rejected`, `paper`, `shadow`, `backtest`, `walk_forward`, `forward_test`, `canary`, `owner_beta`, `live_delivered`, and `live_executed` remain separate in dataset manifests. They must not be merged into a single profitability claim.

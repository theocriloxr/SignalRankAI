# ML bottleneck controls

Owner request, 11 Nov 2026: check every known ML and trading-ML failure mode
against SignalRank and close the gaps. Each row says what protects against it
and where. "n/a" means the failure mode belongs to a model type SignalRank does
not use. SignalRank uses gradient-boosted trees (XGBoost) on tabular features:
no neural network, no generative model and no reinforcement learning.

## What the system trades

| | |
|---|---|
| Asset classes | crypto (OKX/Coinbase/Bybit spot pairs), FX majors and crosses, commodities (gold, silver, WTI), US stocks, indices |
| Signal timeframes | 5m, 15m and 1h; 4h and 1d are used as higher-timeframe context only |
| Trading style | intraday / day trades with TP1-TP3 ladders and a fixed stop |
| ML role | **meta-labelling**: rule-based strategies propose a setup; the model predicts whether that setup reaches TP1 before its stop |
| Execution | paper / signal delivery; live-money execution is off and outside this work |

## Model fit and generalisation

| Failure | Control | Where |
|---|---|---|
| Overfitting | depth 4, min_child_weight 5, gamma, L1/L2, column sampling, early stopping on the calibration window; a stronger small-data profile under 4,000 rows; train-vs-validation AUC gap gate `ML_MAX_OVERFIT_GAP` 0.15 | `ml/train_model.py` |
| Underfitting | AUC ≥ 0.60, balanced accuracy ≥ 0.55, positive recall ≥ 0.20, PR-AUC and expected-R gates: a model that learnt nothing is not promoted | `_promotion_quality_gate` |
| Shortcut learning / spurious correlation | duplicates collapsed to one row per setup per bar; the asset class is recomputed from the symbol, not trusted from stored rows; per-class specialists each pass the full gate on their own class | `ml/train_model.py`, `ml/specialists.py` |
| Catastrophic forgetting | n/a for retrained trees; the champion/challenger flow keeps the serving model until a challenger beats it on the same basis | `_champion_comparison_gate` |

## Data quality

| Failure | Control | Where |
|---|---|---|
| Data leakage / look-ahead | chronological fit → calibration → untouched validation split with a 24 h purge and embargo; features from **closed bars only**, both in training (`_point_in_time_slice`) and live (`closed_candles`); new: any single feature with AUC ≥ 0.90 blocks promotion as a suspected leak | `ml/train_model.py`, `ml/features.py`, `ml/data_audit.py` |
| Data drift / covariate shift | live feature vectors compared with the training baseline (PSI ≥ 0.25 flags a feature); prediction-starvation detection; scheduled daily retrain plus `/ml_retrain` | `ml/drift_monitor.py`, `ml/live_drift.py`, `runtime/analytics.py` |
| Class imbalance | `scale_pos_weight`, imbalance-safe metrics (balanced accuracy, MCC, PR-AUC), threshold chosen on payoff-aware expected R | `ml/train_model.py`, `ml/metrics.py` |
| Curse of dimensionality | rows per feature reported every run; specialists need ≥ 600 own rows | `ml/data_audit.py`, `ml/specialists.py` |
| Label noise | outcomes come from price, not people; new: identical feature rows with opposite outcomes are counted, and a coin-flip share (> 50 % of duplicated rows) blocks promotion | `ml/data_audit.py` |
| Selection / sampling bias | every rejected setup is tracked, not only delivered ones: ML-filtered setups and setups stopped by any later gate, including the final 85 check; one row per setup per bar since 11 Nov, so the labeller covers every distinct setup | `engine/signal_deduplicator.py`, `engine/shadow_outcome_worker.py` |
| Survivorship bias | training uses the system's own logged setups, including assets later removed; external replay uses listed history only and is fit-only (never validation) | `ml/external_replay.py` |
| Feedback loops | shadow (rejected) setups are labelled the same way as delivered ones, so the model also learns from what it blocked | shadow tracker |
| Collinearity / dead features | new: near-duplicate (abs(r) ≥ 0.98) and constant columns reported every run | `ml/data_audit.py` |

## Calibration and deployment

| Failure | Control | Where |
|---|---|---|
| Calibration drift / overconfidence | isotonic calibration fitted on its own window, validated by Brier and ECE on the untouched window, per segment; an uncalibrated model is not certified | `ml/train_model.py` |
| Training-serving skew | live scoring and the shadow scorer share one feature builder (`extract_features` / `build_model_feature_values`); training recomputes candle features from stored candles under the same closed-bar rule; feature-schema migration with strict mode; the live-vs-training drift check catches any remaining skew | `ml/features.py`, `engine/ml.py`, `ml/train_model.py` |
| Silent pipeline failures | dataset log per run (`[ml_dataset]`, `[ml_data_audit]`), last run kept in `runtime_state` (`ml:last_training_run`), stale-model and drought owner alerts, setup-evidence staleness named in the drought alert | `ml/lifecycle_status.py`, `observability/owner_alerts.py` |
| Inference latency / memory | small boosted trees (milliseconds per score) | n/a |
| Reproducibility / experiment sprawl | new: dataset hash and code commit stored with every run's metrics; artifacts versioned in `ml_model_artifacts` with a SHA-256 hash | `ml/data_audit.py`, `ml/model_registry.py` |

## Trading-specific

| Failure | Control | Where |
|---|---|---|
| Fixed-horizon labels | triple-barrier labels: TP1 (win), stop (loss) or expiry, whichever comes first | shadow tracker, `ml/external_replay.py` |
| Random CV leakage | no random or K-fold splits; purged, embargoed chronological windows | `ml/train_model.py` |
| Backtest overfitting / multiple testing | the per-asset scorecard decides on a 99 % interval (about 1,180 cells tested); the setup-evidence filter uses a Wilson lower bound against each plan's own break-even; a model is never promoted on its training window | `services/strategy_scorecard.py`, `services/segment_evidence.py` |
| Expectancy illusion | expected R uses each signal's own TP1 reward, not a fixed 2R | `ml/metrics.py` |
| Regime shifts | regime features and a macro no-trade zone; specialists per asset class; scheduled retrain | engine, `ml/specialists.py` |
| Alpha decay | strategy health baselines with decay limits; 60-day setup evidence; per-asset scorecard | `services/strategy_scorecard.py`, segment evidence |
| Transaction costs / slippage | stop-width, R:R and liquidity gates per class; Asia-session liquidity block | `core/signal_quality_gate.py` |

## How the ML gate decides (since 11 Nov 2026)

`ML_GATE_MODE=auto` (default):

- **Certified class:** a class-specific model passed the full gate on that
  class's untouched validation window. It vetoes at its own certified threshold.
- **Uncertified:** the model only observes. It neither vetoes nor feeds the
  0-100 score. The setup-evidence filter (fail-closed) and the Ultra score floor (`ULTRA_MIN_SCORE`, 80)
  decide, and the signal stays paper-only.

`advisory` treats every candidate as uncertified; `enforce` gives the global
model the veto everywhere.

## Not applicable

The following failure modes don't apply here because the system doesn't use
these technologies:

- vanishing or exploding gradients, dead neurons, mode collapse, saddle points,
  internal covariate shift and FP16 underflow (no neural network);
- context rot, hallucination and model collapse from synthetic data (the AI
  review is advisory and never trained on its own output);
- distributed-training stalls and hardware bit-flips (single-node CPU
  training);
- reward hacking (no reinforcement learning);
- edge-device throttling (server-side only).

# Feature Decisions Locked (2026-04-08)

This file records user-confirmed defaults for advanced feature implementation.

## Exchange Scope
- Native execution exchanges: Binance + Bybit
- Crypto data exchanges: Binance + Bybit

## Smart DCA Profiles
- Profile 1: conservative_swing
  - base_order_usd: 100
  - max_legs: 4
  - initial_spacing_pct: 2.0
  - volume_scale: 1.5
  - step_scale: 1.2
- Profile 2: aggressive_mean_reversion
  - base_order_usd: 50
  - max_legs: 6
  - initial_spacing_pct: 1.5
  - volume_scale: 2.0
  - step_scale: 1.5
- Profile 3: ml_adaptive
  - low_vol_initial_spacing_pct: 1.0
  - low_vol_max_legs: 3
  - high_vol_initial_spacing_pct: 3.5
  - high_vol_step_scale: 1.4

## Trailing Logic
- Activate trailing logic once price moves in favor.

## Paper Trading and UX Defaults
- Simulate all behaviors.
- Chart style default: tradingview.
- Position sizing risk is user-selectable with default 1.0%.

## Sentiment and On-Chain
- Rollout: RSS + Fear/Greed first.
- On-chain alerts include both:
  - exchange inflow/outflow whales
  - dormant wallet moves

## AI Journal and Regime Messaging
- AI journal delivery: automatic (weekly schedule).
- Weekly delivery day: Sunday.

## Correlation Governance
- Correlation filter mode: best_per_cluster.

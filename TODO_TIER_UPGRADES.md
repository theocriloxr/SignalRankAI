# TODO: Tier-Gated Conversion Funnel Upgrades

## Current Status
- [x] Analyze codebase
- [ ] Upgrade 1: Tier-Gated Signal Formatter (Hiding Alpha)
- [ ] Upgrade 2: Daily Limit Enforcer 
- [ ] Upgrade 3: Minimum Score Thresholds

## Upgrade 1: Tier-Gated Signal Formatter
- Add format_free_tiered_signal to tier_signal_formatter.py with:
  - Base info visible (Asset, Direction, Entry)
  - TP1 visible
  - TP2/TP3 locked with 🔒 emoji
  - SL locked with 🔒 emoji
  - ML Confidence locked with 🔒 emoji
  - Tier-gated buttons (MT5 for premium only)

## Upgrade 2: Daily Limit Enforcer
- Already implemented in tier_delivery.py
- Enhance paywall message with better CTA

## Upgrade 3: Minimum Score Thresholds
- Add should_user_receive_signal to filters
- FREE: 80+ score only
- PREMIUM/VIP: All scores pass through

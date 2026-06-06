# TODO - Tier-Gated Conversion Funnel Implementation

## Status: IN PROGRESS

### Upgrade 1: Tier-Gated Signal Formatter
- [ ] Add `format_tiered_signal()` to `signalrank_telegram/tier_signal_formatter.py`
- Gate SL, TP2/TP3, AI Confidence for free users
- Button: Auto-Execute for premium only

### Upgrade 2: Daily Limit Enforcer
- [ ] Add `check_and_enforce_daily_limit()` to `signalrank_telegram/tier_delivery.py`
- Send paywall upsell when free users hit daily limit

### Upgrade 3: Minimum Score Thresholds
- [ ] Update `FREE_MIN_SCORE` from 60 to 80 in `core/tier_constants.py`

---

## Notes
- Free users: 3 signals/day, 80+ score, hidden Alpha (SL/TP2/TP3/ML locked)
- Premium/VIP: Unlimited signals, full data access

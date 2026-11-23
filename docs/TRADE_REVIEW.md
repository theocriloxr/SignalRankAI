# Trade reviews and lessons (23 Nov 2026)

`ml/trade_review.py` reviews every resolved setup the bot has tracked (delivered signals, paper trades,
tracked rejected setups, archived proof, user ideas) every 6 hours (`TRADE_REVIEW_INTERVAL_SECONDS`).

* **Factors** per trade: session, minutes to/from a high-impact release, with/against the 4h and daily
  trend, ADX strength, relative volume, volatility, strategy, timeframe, direction, TP1 reward.
* **Lessons**: per asset class, each factor value's realised R at TP1 versus the rest of that class;
  a lesson needs ≥ 30 trades on each side and a Benjamini-Hochberg q ≤ 0.10 across all tests.
* **Why it worked**: `/why <signal id>` (Telegram), `GET /api/v1/platform/signals/{id}/review`, the
  signal page on the website/app, and a line on every TP/SL outcome message.
* **What it learned**: `/lessons`, `GET /api/v1/platform/learning/lessons`, the Journal page.
* **Self-improvement (tighten-only)**: a context factor (never a whole asset, class or strategy) that
  loses money with high confidence in a class (q ≤ 0.05, ≥ 50 trades, upper 95 % bound of mean R < 0)
  rejects new setups in that context with reason `lesson <factor>=<value>`. Those setups are still
  tracked, so the lesson disappears at the next refresh if it stops being true. `LESSON_GATE_ENABLED=0`
  turns it off. No gate is loosened by this module.

# News handling (15 Nov 2026)

## What the bot does with news

The bot does **not** trade the news release itself. News is used three ways:

1. **Red-news window.** For each high-impact USD release in the economic calendar
   (Forex Factory weekly feed, Finnhub fallback; PPI, CPI, NFP, FOMC, GDP, PCE ...),
   USD-sensitive instruments get a window of 60 minutes before and after the release.
   USD-sensitive means the USD majors, gold, silver, BTC, ETH, US30, NAS100 and US500.
   No signal is delivered inside that window.
2. **Headline sentiment.** Strong sentiment against a setup's direction rejects it
   (`news_conflict`). Sentiment that agrees with the setup adds a small confidence bonus.
3. **ML features.** Each setup records the minutes since and until the nearest
   high-impact release and a 0-1 news-pressure score. The model learns from these.

## Changed on 15 Nov 2026

* **Setups in the window are now built and tracked instead of skipped.** Before, the
  engine skipped the whole asset for two hours around every release and recorded
  nothing, so it could never learn whether trading around news would have paid.
  Now the strategies still run. Each setup is refused with reason
  `news_window <event title>` and tracked to its outcome like every other rejected
  setup, so it joins the training data and the setup-evidence tables.
  `NEWS_WINDOW_TRACK_SETUPS=0` restores the old skip.
* **Exemptions come from evidence.** When tracked outcomes show that setups in the
  window made money for an asset class and timeframe, add that cell to
  `QUALITY_GATE_EVIDENCE_EXEMPTIONS`, for example `news_window:commodity:15m`. The
  same applies to the other gate exemptions (core/gate_evidence.py). There are no
  `news_window` exemptions by default.
* **Nasdaq fix.** The blackout list had `US100`, but the canonical symbol is `NAS100`,
  so the Nasdaq was never blocked around news. It is now.
* **Prop rules.** Funded-account news rules (`core/prop_rules.py`, for example
  FundedNext) are separate and unchanged.

## Deciding whether to trade news

To judge a release such as PPI, compare the tracked `news_window` setups against
setups outside the window. Use the same strategy, asset class and timeframe, and
compare the TP1 rate with the break-even rate. If a cell clears its break-even with
a large enough sample, exempt it. If not, keep the window.

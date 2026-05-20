# Diagnostic Deployment Env Vars

Use these settings temporarily to stop the bot from starving itself while we observe which gate is still blocking signals.

## Safe diagnostic profile

Set these in Railway for the production service:

```bash
PREMIUM_SCORE_THRESHOLD=0
PREMIUM_SCORE_THRESHOLD_FORCE=1
ML_PROB_THRESHOLD=0.0
ML_HARD_FILTER_MIN=0.0
CONFLUENCE_GATE_MIN=0.0
GEMINI_SIGNAL_REVIEW_ENABLED=0
ULTRA_QUALITY_ENABLED=0
EXPECTANCY_HARD_BLOCK_ENABLED=0
CONFLUENCE_DIRECTION_HARD_BLOCK_ENABLED=0
ENGINE_DIAGNOSTIC_DIR=.diagnostics
ENGINE_PIPELINE_DEBUG=1
```

## Why these matter

- `PREMIUM_SCORE_THRESHOLD=0` and `PREMIUM_SCORE_THRESHOLD_FORCE=1` keep DB thresholds from overriding your debug setting.
- `ML_HARD_FILTER_MIN=0.0` removes the hard ML cutoff.
- `GEMINI_SIGNAL_REVIEW_ENABLED=0` disables LLM review during diagnosis.
- `ULTRA_QUALITY_ENABLED=0` disables the ultra-quality filter.
- `EXPECTANCY_HARD_BLOCK_ENABLED=0` stops negative expectancy from hard-blocking entries.
- `CONFLUENCE_DIRECTION_HARD_BLOCK_ENABLED=0` makes confluence directional disagreement advisory instead of fatal.

## What to look for after redeploy

- `final_signals` should move above `0` in engine logs.
- `.diagnostics/heatmap_log.jsonl` should start filling after empty cycles.
- If signals still do not store, the issue is likely in storage or cooldown logic rather than filtering.

## Optional next step

If you want to keep some protection in place, re-enable one gate at a time after the bot starts producing signals again.

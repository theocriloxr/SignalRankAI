# Phase 4 Pass 9 — Automaton and Paper Ecosystem

Date: 2026-07-19  
Status: Safe simulation foundation complete; real execution remains disabled.

`core.automaton` implements a virtual-treasury state machine with OBSERVE,
SIMULATE, PAPER_TRADE, CONSERVE, RECOVER, OPTIMIZE, SCALE, PAUSE, and
KILL_SWITCH states. It responds to drawdown, expectancy, sample size, provider
confidence, and dependency health with auditable recommendations only.

`services.ecosystem_policy` adds explicit paper-fill assumptions, deterministic
order identities, consent records, copy-trade fail-closed decisions, and
portfolio snapshots. `execution.service.ExecutionGate` remains the only future
broker hand-off and requires every safety gate plus default-off flags.

No automaton action submits a broker order, enables copy trading, or moves
funds. Paper PnL is not cash.

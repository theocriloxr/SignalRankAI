# Full System Stabilization Fix — 2026-07-10

This patch addresses the latest production symptoms:

- Telegram inline callbacks reached the webhook but were answered too late. Added an immediate group=-100 callback ACK guard.
- `/signals` could block until the 60s command timeout. Added bounded DB timeouts and smaller active-delivery query limits.
- Signal messages exposed internal Gemini degradation strings. Added user-safe AI review wording.
- Manual execution profiles were receiving auto-close wording. TP wording now follows execution mode.
- Risk/Reward showed profile minimum values instead of the actual target-derived RR. Formatter now prefers computed RR.
- Engine Pulse delivery count could undercount successful delivery proof writes. Delivery count now uses robust DB proof columns.

No DB migration is required.

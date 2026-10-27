# SignalRankAI motion

- **Tier 0**: all risk, trade, execution, balances, P&L, status, security, alerts, approvals, money and broker UI. No decorative movement or delayed state transitions.
- **Tier 1**: hover/focus and buttons, 100–220ms or none.
- **Tier 2**: mobile disclosure/drawer if warranted, up to 250ms; use native HTML where possible.
- **Tier 3**: public educational sections only; static fallback and full reduced-motion pathway.
- **Tier 4**: cinematic/canvas effects not approved for the live terminal. Added implementation currently uses **zero additional animation packages**.
- `prefers-reduced-motion: reduce` and low-power devices must see complete content and usable actions. No infinite stock ticker or flashing profit figures.

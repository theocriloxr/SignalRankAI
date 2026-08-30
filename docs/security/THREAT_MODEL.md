# THREAT_MODEL — SignalRankAI

Scope: Telegram front door, Paystack payments, signal engine, delivery,
outcome/ledger services, providers, admin tooling. Assets: user funds
(disabled real-money paths), credentials, trading data, financial truth,
availability.

## Threats and mitigations

| # | Threat | Likelihood | Impact | Mitigation | Status |
|---|---|---|---|---|---|
| TM-01 | Credential theft (API/bot/provider keys) | M | H | secrets in env only, no logging of tokens/keys/signatures, redaction tests, rotation | Mitigated |
| TM-02 | Account takeover / broken authorization | M | H | RBAC, owner/admin gates on every ops command, `/capabilities` redacted | Mitigated (commands), web MFA pending |
| TM-03 | Webhook forgery | M | H | Paystack signature verified from raw body, durable persist, HTTP 200 after persist | Mitigated |
| TM-04 | Replay / duplicate financial effect | M | H | idempotency keys, `IdempotentInbox`, ledger duplicate rejection, stream dedupe | Mitigated |
| TM-05 | Queue poisoning / poison record | M | M | per-item savepoints, DLQ, poison isolation, sanitized errors | Mitigated |
| TM-06 | Event / ledger tampering | L | H | immutable envelope + payload_hash, append-only ledger, fingerprint | Mitigated (V2.0 layer) |
| TM-07 | Market-data poisoning | M | M | provenance + source timestamp, cross-provider deviation, typed failures | Mitigated |
| TM-08 | Provider compromise | M | H | capability-specific flags, quarantine, no withdrawal-capable keys used | Partial (execution disabled) |
| TM-09 | Dependency compromise | L | H | pinning + SBOM pipeline required (TD-008) | Open |
| TM-10 | Insider misuse | M | H | audited ops commands, owner allowlists, immutable audit trail | Mitigated |
| TM-11 | Private-key compromise (wallets/brokers) | L | H | envelope encryption requirement, IP allowlisting, hot-wallet minimization | Open (SR-SEC-004) |
| TM-12 | Prompt injection via news/provider text | M | M | LLM summaries never treated as verification; provenance retained | Partial |
| TM-13 | Trading manipulation / spoofing | M | H | execution disabled; risk breakers; heuristic labels | N/A while disabled |
| TM-14 | DoS / resource exhaustion | M | M | bounded queues, backpressure, admission control, rate limits | Mitigated |
| TM-15 | Cross-tenant data leakage | M | H | tenant identity in envelope; per-tenant quota/queries (web layer pending) | Partial |
| TM-16 | Fraudulent strategy publishers | M | M | marketplace DISABLED; publisher verification required before enablement | N/A |

## Residual risk summary

Live execution, copy trading, marketplace, broker credential storage and the
web surface remain disabled or pending the items in
`BLOCKED_EXTERNAL_REQUIREMENTS.md`. Mitigations listed above are effective in
the deployed staging boundary and must be re-verified before any
real-money feature is activated.

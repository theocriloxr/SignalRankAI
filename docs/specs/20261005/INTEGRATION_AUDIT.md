# October 5 integration audit

The five user directives in this directory are preserved without modification.
`source-manifest.json` records their attachment IDs, SHA-256 hashes and all 560
numbered sections. Empty evidence arrays indicate that no completion claim has
been made for that section. This inventory is not a completed acceptance ledger.

## Account identity and client recovery

The canonical account snapshot now recognizes an active, verified Telegram
authentication identity when the legacy user Telegram ID is absent. Disabled or
unverified identities do not satisfy that check. Pending account-history review
remains distinct from an ordinary linked account. Ownership is not transferred
and no legacy histories are automatically merged by this change.

Link-code creation rechecks canonical state under the user row lock, including
non-HTTP callers. Already verified accounts receive a conflict rather than a new
code. Only active, unexpired pending requests determine pending status; expiry
uses an explicit UTC timestamp, independent of the database session timezone.

Web and native clients recognize the canonical linked state and refresh on return
from Telegram. The browser preserves unsaved profile edits and user navigation
during delayed startup. Mobile exposes structured API errors and retains the
current account during transient refresh failures. The offline shell generation
was advanced together with its asset references.

Local validation on October 5:

- 116 backend regression tests passed, including real isolated PostgreSQL identity,
  disabled/unverified identity, expiry, legacy-link and reviewed-merge cases.
- 11 mobile Node contract tests passed; TypeScript passed without errors.
- Critical Python typing passed with zero errors and warnings.
- Six real local HTTP/PostgreSQL Chromium journey checks passed across desktop and
  mobile viewports. These used synthetic local identities and did not send
  Telegram commands or broker orders. Native-device and external Telegram proof
  have not been established by these checks.

## Release transport

A credential-free Railway API probe reproduced HTTP 403 with Python's default
user agent and HTTP 200 with `SignalRankAI-ReleasePreflight/1.0`. Release API
requests now identify the application. Hosted credential validity and scope must
still be established by the exact-commit preflight; the transport probe alone
does not prove that the supplied production token is valid.

## Fresh findings still being worked

- The Next.js public landing page is no longer the default starter. Its
  authenticated overview and catch-all pages still describe capabilities without
  fetching and presenting their canonical backend state. Those pages are not a
  completed replacement for the serving legacy application.
- Provider fallback, request caches and live indicator inputs now reject stale,
  future and structurally invalid candle windows before accepting a provider.
  Historical validation remains separate and accepts an explicit observation
  time. Both async and sync paths use the registered asset-class chain, honor
  explicit provider allowlists and exclude unconfigured or disabled feeds.
  These changes passed 125 focused regressions including the FCS v4 contract.
- The FCS candle adapter used an undocumented guessed endpoint and response
  format. It now uses the documented v4 history endpoint, preserves source
  timestamps, sends credentials in the POST body and redacts provider errors.
  A read-only production-key probe at 21:21 UTC on October 5 returned 200 valid
  fresh EURUSD candles. XAUUSD returned valid stale candles, and AAPL/NAS100
  returned provider code 213 with no candles. This proves FX access only; it
  does not certify broker execution or all market classes. Contract reference:
  https://fcsapi.com/document/forex-api
- The configured equity feed rejected a current-day AAPL aggregate request with
  HTTP 403 / `NOT_AUTHORIZED`; crypto passed the open-session certification, but
  the other required asset classes did not.
- The existing long-running production observation retains failed samples and
  covers the older deployed release. It cannot certify a changed candidate.
- Multi-account routing, aggregate risk, research evidence, all customer routes
  and native flows require verification against the directives; file existence
  and old implementation labels are insufficient proof.

## Research input access

The referenced Google document could not be retrieved through its mobilebasic,
text-export, preview or edit URLs during this audit. Its contents have not been
reviewed, and no extraction or document-specific implementation is claimed.

No real-money readiness, subsystem score, completed soak, external broker fill,
production promotion or overall completion is claimed by this audit.

Hosted CI for commit 99d67ae8 passed the Railway credential preflight and static
security checks. Backend gates identified a stale generated file inventory,
which is regenerated with this change. Frontend and mobile audit gates still
reported five and sixteen high dependency findings respectively. Failed gates
are retained; no production approval or audit waiver has been issued.

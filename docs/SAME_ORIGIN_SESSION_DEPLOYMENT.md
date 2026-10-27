# SignalRankAI web session routing and CSRF — staging acceptance

## Architecture (source contract)
The **browser** uses relative `/api/v1/platform/...` URLs and `credentials: include`. Next.js rewrites this **exact** API prefix to the trusted backend origin from a **server-only** environment variable:

`SIGNALRANK_PLATFORM_API_ORIGIN=https://<trusted-api-host>`

This variable is set **on the Next.js frontend deployment**; it must contain only an HTTPS origin (no path, credentials, query or fragment). For local development only, `http://localhost` and loopback are supported. The browser no longer uses `NEXT_PUBLIC_SIGNALRANK_API_BASE_URL` for sessions.

The backend must keep `APP_COOKIE_SECURE=1`, `APP_COOKIE_DOMAIN` empty for host-only cookies when requests are proxied to the frontend hostname, and cookie path `/`; its existing `SameSite=Lax` session+CSRF cookies then belong to the frontend host. **Do not disable CSRF** and do not set `SameSite=None` merely to bypass an incorrect proxy setup. Ensure the backend's public application base URL points to the frontend for email activation and password links. Keep API and frontend HTTPS throughout.

If the trusted origin is missing, the frontend does **not** silently forward account data to an arbitrary public host. Protected API requests fail with 404 until the setting is supplied. This is an intentional configuration block, not a successful connectivity check.

## Mandatory deployed proof (before signing off)

1. Create a **staging-only** Next deployment with the server-only origin set to the matching staging API. Do not point staging at production or share staging/prod DB/Redis.
2. Visit /login and register a disposable staging account. Verify the network request goes to the **same frontend host** at `/api/v1/platform/auth/register` and the response issues `sr_access`, `sr_refresh`, `sr_session` (HttpOnly, Secure), and `sr_csrf` (readable, Secure). Do not copy these values into bug reports, screenshots or logs.
3. Confirm `document.cookie` sees only the CSRF cookie, **never access/refresh/session**; verify `/api/v1/platform/me` authenticates via the proxy.
4. Submit a staging watchlist/support/journal write; require `X-CSRF-Token` matching the readable cookie, a corresponding 201/200 from backend, and a persisted account-owned row. A missing or wrong CSRF token must fail.
5. Test cross-account isolation, 401 expired sessions, 403 restricted entitlements, refresh-cookie rotation, re-login and logout cookie clearing. Magic-link email scanners must not consume tokens automatically; verification happens only after user click.
6. Verify no PII/token leakage to query logs, browser storage, cross-origin URLs, monitoring or client-side error payloads.
7. Check deployment redirects after broker secure-link setup, particularly return URL and no old localhost origin. Any flow requiring a true connected broker must use a **demo** account first and must **not** authorize order placement.
8. Record deployment commit SHA, source environment fingerprint, results, timestamp, reviewer, browser/device evidence, failed cases and rollbacks in the release evidence ledger.

## Release blocker if unsupported
Some deployment providers may not preserve `Set-Cookie` and `Host` behavior through their reverse proxy; confirm these semantics in **actual browser + staging**. If host-only cookies do not work, correct the trusted deployment routing. **Never** fall back to JavaScript access tokens or remove CSRF solely to make login appear successful.

This document describes a code-level configuration contract and acceptance procedure. It does not claim that staging session/cookie/cross-domain tests already passed.

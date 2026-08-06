# Security and Identity Contract

## Canonical identity rules

1. One canonical user can own many verified identities.
2. `(provider, provider_subject_id)` is unique.
3. Telegram chat IDs never become authorization credentials for web/mobile.
4. Linking requires both a recently authenticated app session and a one-time
   Telegram confirmation.
5. Ambiguous duplicates enter review; they are not auto-merged.
6. A user cannot unlink the only remaining login method.

## Tokens and sessions

- Access tokens are short-lived HMAC-SHA256 compact tokens with strict canonical
  Base64URL decoding.
- Refresh tokens are opaque, hashed in PostgreSQL, rotated on use and grouped in
  revocable session families.
- Cookie authentication uses `Secure`, `HttpOnly`, `SameSite=Lax` and a separate
  CSRF token.
- Mobile credentials belong in OS secure storage, never AsyncStorage.
- Login and linking attempts are rate-limited and recorded as security events.

## Secrets

- Provider, webhook and push credentials are encrypted using the existing
  application encryption service.
- API keys are shown once; only their hashes and prefixes are retained.
- Webhook signing secrets are shown once and encrypted at rest.
- Execution credentials never activate execution without a separate explicit
  flag, certification, entitlement, opt-in and risk approval.

## Required production values

- `APP_AUTH_SECRET`: at least 32 random characters.
- `ENCRYPTION_KEY`: valid application encryption key.
- `APP_COOKIE_SECURE=1`.
- Explicit CORS allowlist.
- Separate staging and production bot tokens, databases, Redis and OAuth clients.

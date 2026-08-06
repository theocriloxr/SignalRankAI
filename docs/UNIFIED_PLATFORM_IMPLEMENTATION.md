# SignalRankAI Unified Platform Implementation

Release: `v1.4.2-unified-ecosystem-20260806`

## Architecture

SignalRankAI now uses one canonical `users.id` across Telegram, the responsive
web/PWA client, the Expo mobile client, subscriptions, signal deliveries, paper
positions, journals, API keys, webhooks and organization workspaces. Telegram
chat IDs are identities, not primary account keys.

## Implemented cross-channel flows

- Existing Telegram users can request `/app` or `/login_code` and receive a
  short-lived, single-use activation challenge.
- App-created users can generate a one-time Telegram link code and complete it
  with `/link CODE` or a Telegram deep link.
- A Telegram identity already attached to a legacy user is never silently
  overwritten. The system writes a `pending_review` merge record.
- Passwords use salted scrypt hashes; permanent passwords are never sent by the
  bot.
- Web sessions use secure HttpOnly cookies, CSRF protection and rotating refresh
  tokens. Mobile refresh tokens are stored with Expo SecureStore.
- Telegram Login Widget and Mini App init-data signatures are verified on the
  server.

## Product surfaces

- `/app`: responsive authenticated web application and installable PWA.
- `/api/v1/platform`: unified REST API for identity, dashboard, signals,
  instruments, watchlists, paper positions, journal, devices, preferences,
  subscription entitlements, webhooks, organizations and support.
- `mobile/`: Expo Android/iOS source sharing the same backend identity and data.
- Professional API keys use scoped, hashed secrets and separate rate limits.
- Outbound webhooks are encrypted at rest, HMAC-signed, retryable and protected
  against private-network SSRF targets.

## Trading integrity

The app does not create a second trading engine. It consumes canonical signals,
deliveries, outcomes, instruments and paper positions from the existing backend.
No live execution route was enabled by this release.

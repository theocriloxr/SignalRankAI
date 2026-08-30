# SignalRankAI v1.5.0 Account Email and MFA

## Included flows

- Email/password registration and login.
- Email verification using a hashed, expiring, single-use challenge.
- Magic-link login with the same one-time challenge rules.
- Password reset with session-family revocation after completion.
- TOTP authenticator MFA.
- One-time recovery codes stored only as hashes.
- MFA login challenges that expire and cannot be replayed.
- Device/session listing and per-device or global revocation.
- Telegram-to-app activation and app-to-Telegram linking.

## Email delivery

Account actions are committed to `email_outbox` before delivery. The worker
claims rows with `FOR UPDATE SKIP LOCKED`, sends SMTP outside the database
transaction, and stores a terminal or retryable result.

Required staging variables:

```env
EMAIL_DELIVERY_ENABLED=1
EMAIL_FROM=SignalRankAI <no-reply@your-domain.example>
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_USE_SSL=0
SMTP_USE_STARTTLS=1
SMTP_TIMEOUT_SECONDS=15
EMAIL_MAX_ATTEMPTS=6
```

Missing SMTP configuration leaves messages queued and does not pretend they
were sent.

## Security rules

- Never send permanent passwords through Telegram or email.
- Keep `APP_AUTH_SECRET` and `ENCRYPTION_KEY` separate and random.
- Rotate secrets through a controlled session-revocation process.
- Require HTTPS in staging and production.
- Set `APP_BASE_URL` to the exact first-party application origin.
- Verify the sending domain's SPF, DKIM and DMARC records before public launch.
- Store recovery codes offline; the application only returns them once.

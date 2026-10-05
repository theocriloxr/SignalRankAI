# SignalRankAI Mobile

React Native/Expo source for Android and iOS. It uses the same canonical account and API as Telegram and the PWA.

## Configure

```bash
cp .env.example .env
npm install
npm run typecheck
npx expo start
```

A development build is required for remote push notifications on current Android Expo SDKs.

## Security

- Access and refresh tokens are stored with `expo-secure-store`, not AsyncStorage.
- Native requests explicitly omit browser cookies. Mobile session issuance and
  refresh return bearer tokens without issuing cookie sessions, and mobile
  refresh requires its own token rather than borrowing an ambient browser
  cookie. Browser/PWA sessions retain cookie and CSRF protection.
- Refresh tokens rotate server-side and reuse revokes the session family.
- Sign-out immediately blocks late account/login/refresh responses and removes
  the local token pair. It also posts the refresh proof to
  `/api/v1/platform/auth/logout-mobile`, which revokes that device's whole
  rotation family, including a successor created during sign-out. Other device
  families remain active. Token rotation and family revocation share an account
  row lock in PostgreSQL.
- Offline sign-out still removes local credentials. If server revocation or
  secure-store deletion cannot be confirmed, the sign-in screen explains how
  to revoke the device from Security; it does not claim remote sign-out passed.
- Live execution is not enabled by credentials or by the mobile client.

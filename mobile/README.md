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


## Native redesign (9 October 2026 candidate)

The Expo application now exposes fourteen account/workflow destinations through four primary bottom tabs and a scrollable, touch-accessible More panel: overview, signals, markets, paper, portfolio, performance, journal, support, account, brokers, notifications, watchlists, alerts and research.

The app follows Expo `userInterfaceStyle: automatic` and applies the SignalRank-approved emerald/silver palette for both system dark and system light appearances. This is **system-based appearance**; a persisted manual override is not yet implemented. VoiceOver/TalkBack, font scaling, iOS/Android small-screen and tablet evidence must be collected on actual devices before an accessibility pass is signed.

Financial labels never invent a default USD currency, unknown account balance, guaranteed win rate or completed broker trade. Paper data is explicitly simulated. Delivered-signal detail shows receipt provenance; connected brokerage inventory is informational. Custom-alert actions are monitoring-only and require canonical account approval; disablement requires a separate confirmation. Watchlists use canonical instrument identity.

Native source contract tests live in `scripts/presentation-contract.test.cjs` and run alongside the existing account/session and dependency tests through `npm run test:dependencies`. **Hosted evidence:** run `37890335474` passed TypeScript and **53** mobile source/dependency tests for the then-current candidate; its security audit still **failed** on four inherited Expo/`node-forge` high-severity advisories, so this is not a mobile release approval. Subsequent source commits need exact-head checks.

Full financial feature parity is a separate release requirement. Real demo-broker sessions, native binary signing, push/deep links, secure-store behavior on physical devices and a clean mobile dependency audit remain to be certified. Do not enable live execution or replace missing data with demo-looking values to complete a visual review.

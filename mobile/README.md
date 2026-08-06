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
- Refresh tokens rotate server-side and reuse revokes the session family.
- Live execution is not enabled by credentials or by the mobile client.

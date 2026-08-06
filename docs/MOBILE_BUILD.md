# Mobile Build Guide

The `mobile/` project is an Expo/React Native client for Android and iOS.

## Local development

```bash
cd mobile
npm install
cp .env.example .env
npm run start
```

Set `EXPO_PUBLIC_API_BASE_URL` to the staging API for development builds.

## Build preparation

1. Create separate Expo/EAS projects for staging and production.
2. Add Android package and iOS bundle identifiers owned by SignalRankAI.
3. Configure staging and production API URLs separately.
4. Configure Expo push credentials, Apple APNs and Firebase/FCM.
5. Use EAS secrets for build-only credentials.
6. Produce internal Android builds and TestFlight builds before store release.
7. Complete privacy labels, risk disclosures, support URL and account-deletion
   flow before submission.

The repository does not include Apple certificates, Google Play signing keys,
APNs/FCM credentials or an EAS project ID because those must belong to the
project owner.

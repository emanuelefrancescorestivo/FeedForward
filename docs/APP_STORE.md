# App Store Submission Guide (Phase 4)

> **Status: future checklist, not done.** The project is not deployed and has not
> been submitted to any store. Kept as the list of what shipping would require.

Health apps face stricter review than most categories. This is the concrete path
from working code to a live listing on both stores.

## Accounts & cost

| Item | Cost | Notes |
|------|------|-------|
| Apple Developer Program | $99 / year | Required to ship to the App Store / TestFlight |
| Google Play Console | $25 one-time | Required to ship to Play |

## Pre-submission checklist

### Legal & policy (do these first — they block review)
- [ ] **Privacy policy** hosted at a public URL. Required by both stores. Must
      state what data is collected (account email, saved goals) and how it's used.
- [ ] **Terms of service** including the health disclaimer.
- [ ] **GDPR compliance** (you're EU-based): lawful basis for processing, data
      export/delete on request, no unnecessary collection. The in-memory user
      store must be replaced with a real database that supports deletion.
- [ ] **No medical claims** anywhere in copy, screenshots, or metadata. Use
      "supports", "associated with", "may help" — never "treats", "cures",
      "prevents". The in-app disclaimer already reflects this.

### Apple-specific
- [ ] `NSHealthShareUsageDescription` — only if you integrate HealthKit (v1 does
      not; the placeholder in `app.json` says so).
- [ ] Health & Fitness category apps must not provide inaccurate medical
      information — the evidence grading and disclaimers are your defence here.
- [ ] App Privacy "nutrition label" in App Store Connect: declare data types.
- [ ] Screenshots for all required device sizes.

### Android-specific
- [ ] Data safety form in Play Console.
- [ ] Target the current API level required by Play.
- [ ] Health apps: declare in the Health category and follow the health content
      policy.

## Build & release pipeline (Expo/EAS)

```bash
cd mobile
npm install -g eas-cli
eas login

# Configure (creates eas.json)
eas build:configure

# TestFlight / internal testing builds
eas build --platform ios --profile preview
eas build --platform android --profile preview

# Production builds
eas build --platform all --profile production

# Submit to stores
eas submit --platform ios
eas submit --platform android
```

## Beta before public

1. **TestFlight** (iOS) and **Play internal testing** (Android) with 10–20 real
   users. Health apps especially benefit from real dietary edge cases.
2. Collect feedback on the explanations — the core value is whether people
   *trust and understand* the reasoning.
3. Fix, then submit for public review.

## Review timelines

- Apple: typically 1–3 days; health apps can take longer or get extra scrutiny.
- Google: hours to a few days.

## Backend readiness before launch

The reference backend uses an in-memory user store and `allow_origins=["*"]`.
Before public launch:

- [ ] Move users/subscriptions to **PostgreSQL** (schema: users, saved_goals,
      subscriptions).
- [ ] Deploy the graph cache to **Redis** (the precomputed reverse-Dijkstra
      results) so multiple API instances share it.
- [ ] Restrict CORS to your app's origins.
- [ ] Set `FEEDFORWARD_SECRET` to a strong secret; rotate JWT keys.
- [ ] Rate-limit the public endpoints.
- [ ] Add monitoring/alerting on the API.

## What "done" looks like for v1

A user can: create an account, browse goals by system, get explained
recommendations with visible evidence, filter by diet, build a calorie-bounded
meal, and (as a professional) see full grades and citations — running against a
production API, listed on both stores.

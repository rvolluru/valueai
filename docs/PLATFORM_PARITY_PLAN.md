# Platform Parity Plan (Web + Mobile Web + Mobile App)

## Objective

Deliver one consistent Jouft product across:

- Desktop web (`apps/web`)
- Mobile web (responsive `apps/web`)
- Native mobile app (`apps/mobile`, Expo/React Native)

## Product Contract

- Single backend contract: `apps/api` (`/v1/*`)
- Single auth model: `x-api-key` (dev) and `Authorization: Bearer <token>` (Clerk/prod)
- Shared API client/types package: `packages/app-client`
- Platform-specific UI only where required (navigation, gestures, native capabilities)

## Phase Plan

1. Foundation (this phase)
   - Add shared API client/types scaffold.
   - Define parity checklist and ownership.
2. Mobile Web Hardening
   - Validate every major screen at 360px, 390px, 430px widths.
   - Remove overflow/stacking issues and touch target regressions.
3. Native Parity
   - Port Marketplace, Trade Inbox, Profile, Subscription, and Shipping flows into `apps/mobile`.
   - Reuse shared API package for all network calls.
4. Mobile Platform Features
   - Deep linking, push notifications, camera permissions, share sheets.
   - Error handling/retry for trade + shipping label flows.
5. Release
   - Web CI/CD (existing) + EAS build and release lanes for iOS/Android.

## Parity Checklist

Legend:

- `DONE` complete
- `IN PROGRESS` partially implemented
- `TODO` not implemented yet

| Capability | Web | Mobile Web | Native App |
| --- | --- | --- | --- |
| Auth (sign in / sign up) | DONE | DONE | IN PROGRESS |
| Create listing wizard | DONE | DONE | DONE |
| Marketplace browsing | DONE | DONE | TODO |
| Start trade flow | DONE | DONE | TODO |
| Trade inbox actions | DONE | DONE | TODO |
| Shipping addresses (multiple) | DONE | DONE | TODO |
| Shipping quote + labels | DONE | DONE | TODO |
| Subscription plans | DONE | DONE | TODO |
| Payment methods (Stripe) | DONE | DONE | TODO |
| Profile / style preferences | DONE | DONE | TODO |
| Share listing to social | IN PROGRESS | IN PROGRESS | TODO |
| Push notifications | TODO | TODO | TODO |

## Technical Tasks

1. Move duplicated API logic from `apps/web/src/App.jsx` and `apps/mobile/App.js` into `packages/app-client`.
2. Add shared response/shape typedefs and normalize error handling.
3. Add platform adapters:
   - Web: use browser `fetch`.
   - Mobile: use RN `fetch` + native file upload compatibility.
4. Add thin app-level hooks/wrappers:
   - `apps/web/src/lib/apiClient.js`
   - `apps/mobile/src/lib/apiClient.js`
5. Add contract tests for shared client request/response behavior.

## Definition of Done

- All core user flows work on desktop web, mobile web, and native app.
- Shared client package handles all `/v1/*` calls used by UI apps.
- No platform has a blocking regression in auth, listings, offers, or shipping.

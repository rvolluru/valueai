# @valueai/app-client

Shared API client scaffold for Jouft web/mobile surfaces.

## Purpose

- Keep request/auth/error logic in one place.
- Reuse endpoint wrappers between `apps/web` and `apps/mobile`.
- Reduce drift between web and native behavior.

## Current Surface

- Generic helpers: `buildAuthHeaders`, `resolveApiUrl`, `requestJson`
- Client factory: `createApiClient`
- Endpoint wrappers:
  - Listings (`listListings`, `listMyListings`, `listMarketplace`, `createListing`, `updateListing`)
  - Analysis (`analyzeItem`)
  - Offers (`createOffer`, `incomingOffers`, `offerAction`, `listOfferCandidates`)
  - Profile (`profileQuiz`, `saveProfileQuiz`)
  - Payments (`paymentMethods`, `createSetupCheckoutSession`, `syncStripePaymentMethods`)

## Example

```js
import { createApiClient } from "@valueai/app-client";

const client = createApiClient({ apiBaseUrl: "http://127.0.0.1:8000" });
const listings = await client.listMarketplace(50, { apiKey: "local-dev-key" });
```

## Next Step

Wire app-specific modules to this package:

- `apps/web/src/lib/apiClient.js`
- `apps/mobile/src/lib/apiClient.js`

function normalizeBaseUrl(apiBaseUrl) {
  return String(apiBaseUrl || '').replace(/\/$/, '');
}

function buildAuthHeaders(auth = {}) {
  const bearer = (auth.bearerToken || '').trim();
  if (bearer) return { Authorization: `Bearer ${bearer}` };
  const apiKey = (auth.apiKey || '').trim();
  if (apiKey) return { 'x-api-key': apiKey };
  return {};
}

async function parseJsonOrNull(resp) {
  try {
    return await resp.json();
  } catch {
    return null;
  }
}

function errorDetail(payload) {
  if (!payload) return null;
  if (Array.isArray(payload.detail)) return payload.detail[0]?.msg || payload.detail[0] || null;
  return payload.detail || null;
}

async function requestJson({ apiBaseUrl, path, method = 'GET', auth = {}, body, headers = {} }) {
  const url = `${normalizeBaseUrl(apiBaseUrl)}${path}`;
  let resp;
  try {
    resp = await fetch(url, {
      method,
      headers: {
        ...buildAuthHeaders(auth),
        ...headers,
      },
      body,
    });
  } catch (e) {
    const baseUrl = normalizeBaseUrl(apiBaseUrl);
    throw new Error(`Network request failed connecting to ${baseUrl}. ${e?.message || ''}`.trim());
  }
  const payload = await parseJsonOrNull(resp);
  if (!resp.ok) {
    throw new Error(errorDetail(payload) || `API error (${resp.status})`);
  }
  return payload;
}

export function createMobileApiClient({ apiBaseUrl }) {
  return {
    async analyzeItem({ images = [], category, userCondition, itemDescription, debug = true }, auth = {}) {
      const fd = new FormData();
      images.forEach((img, idx) => {
        fd.append('images', {
          uri: img.uri,
          name: img.fileName || `upload-${idx + 1}.jpg`,
          type: img.mimeType || 'image/jpeg',
        });
      });
      if (category) fd.append('category', category);
      if (userCondition) fd.append('user_condition', userCondition);
      if (itemDescription) fd.append('item_description', itemDescription);
      fd.append('debug', String(Boolean(debug)));
      return requestJson({
        apiBaseUrl,
        path: '/v1/analyze',
        method: 'POST',
        auth,
        body: fd,
      });
    },
    async uploadImages({ images = [], itemId = '' }, auth = {}) {
      const fd = new FormData();
      images.forEach((img, idx) => {
        fd.append('images', {
          uri: img.uri,
          name: img.fileName || `upload-${idx + 1}.jpg`,
          type: img.mimeType || 'image/jpeg',
        });
      });
      if (itemId) fd.append('item_id', itemId);
      return requestJson({
        apiBaseUrl,
        path: '/v1/uploads/images',
        method: 'POST',
        auth,
        body: fd,
      });
    },
    async queueListingAnalysis({ listingId, images = [], imageUrls = [], category, userCondition, itemDescription, itemSize, debug = true }, auth = {}) {
      const fd = new FormData();
      images.forEach((img, idx) => {
        fd.append('images', {
          uri: img.uri,
          name: img.fileName || `upload-${idx + 1}.jpg`,
          type: img.mimeType || 'image/jpeg',
        });
      });
      if (Array.isArray(imageUrls) && imageUrls.length > 0) fd.append('image_urls_json', JSON.stringify(imageUrls));
      if (category) fd.append('category', category);
      if (userCondition) fd.append('user_condition', userCondition);
      if (itemDescription) fd.append('item_description', itemDescription);
      if (itemSize) fd.append('item_size', itemSize);
      fd.append('debug', String(Boolean(debug)));
      return requestJson({
        apiBaseUrl,
        path: `/v1/listings/${encodeURIComponent(listingId)}/analysis-jobs`,
        method: 'POST',
        auth,
        body: fd,
      });
    },
    createListing(payload, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: '/v1/listings',
        method: 'POST',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    },
    updateListing(listingId, payload, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: `/v1/listings/${encodeURIComponent(listingId)}`,
        method: 'PUT',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    },
    deleteListing(listingId, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: `/v1/listings/${encodeURIComponent(listingId)}`,
        method: 'DELETE',
        auth,
      });
    },
    listListings(params = {}, auth = {}) {
      const query = new URLSearchParams();
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') query.set(key, String(value));
      });
      const suffix = query.toString() ? `?${query.toString()}` : '';
      return requestJson({
        apiBaseUrl,
        path: `/v1/listings${suffix}`,
        method: 'GET',
        auth,
      });
    },
    listMarketplace(limit = 50, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: `/v1/listings?limit=${limit}&include_matches=true`,
        method: 'GET',
        auth,
      });
    },
    listMyListings(limit = 100, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: `/v1/listings?mine=true&limit=${limit}`,
        method: 'GET',
        auth,
      });
    },
    listOfferCandidates(targetListingId, limit = 100, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: `/v1/listings/${encodeURIComponent(targetListingId)}/offer-candidates?limit=${limit}`,
        method: 'GET',
        auth,
      });
    },
    createOffer(payload, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: '/v1/offers',
        method: 'POST',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    },
    incomingOffers(status = 'pending', limit = 50, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: `/v1/offers/incoming?status=${encodeURIComponent(status)}&limit=${limit}`,
        method: 'GET',
        auth,
      });
    },
    actionOffer(offerId, status, receiveAddress = null, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: `/v1/offers/${encodeURIComponent(offerId)}/action`,
        method: 'POST',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status, receive_address: receiveAddress }),
      });
    },
    fetchShippingLabels(offerId, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: `/v1/offers/${encodeURIComponent(offerId)}/shipping-labels`,
        method: 'GET',
        auth,
      });
    },
    fetchShippingQuote(offerId, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: `/v1/offers/${encodeURIComponent(offerId)}/shipping-quote`,
        method: 'POST',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
    },
    createShippingLabels(offerId, rateId = null, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: `/v1/offers/${encodeURIComponent(offerId)}/shipping-labels`,
        method: 'POST',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmed: true, rate_id: rateId || null }),
      });
    },
    fetchShippingLabelDocument(shipmentId, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: `/v1/shipments/${encodeURIComponent(shipmentId)}/label`,
        method: 'GET',
        auth,
      });
    },
    fetchProfileQuiz(auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: '/v1/me/profile-quiz',
        method: 'GET',
        auth,
      });
    },
    saveProfileQuiz(payload, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: '/v1/me/profile-quiz',
        method: 'PUT',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload || {}),
      });
    },
    fetchClientState(auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: '/v1/me/client-state',
        method: 'GET',
        auth,
      });
    },
    saveClientState(payload, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: '/v1/me/client-state',
        method: 'PUT',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload || {}),
      });
    },
    addressSuggestions({ q = '', city = '', state = '', postalCode = '' } = {}, auth = {}) {
      const query = new URLSearchParams();
      if (q) query.set('q', q);
      if (city) query.set('city', city);
      if (state) query.set('state', state);
      if (postalCode) query.set('postal_code', postalCode);
      return requestJson({
        apiBaseUrl,
        path: `/v1/usps/address-suggest?${query.toString()}`,
        method: 'GET',
        auth,
      });
    },
    paymentMethods(auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: '/v1/me/payment-methods',
        method: 'GET',
        auth,
      });
    },
    deletePaymentMethod(paymentMethodId, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: `/v1/me/payment-methods/${encodeURIComponent(paymentMethodId)}`,
        method: 'DELETE',
        auth,
      });
    },
    setDefaultPaymentMethod(paymentMethodId, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: `/v1/me/payment-methods/${encodeURIComponent(paymentMethodId)}/default`,
        method: 'POST',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
    },
    createSetupCheckoutSession(payload, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: '/v1/me/payment-methods/stripe/setup-checkout-session',
        method: 'POST',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload || {}),
      });
    },
    createSetupIntent(auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: '/v1/me/payment-methods/stripe/setup-intent',
        method: 'POST',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
    },
    syncStripePaymentMethods(auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: '/v1/me/payment-methods/stripe/sync',
        method: 'POST',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
    },
    activateSubscription(payload, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: '/v1/me/subscription/activate',
        method: 'POST',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload || {}),
      });
    },
  };
}

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
  const resp = await fetch(url, {
    method,
    headers: {
      ...buildAuthHeaders(auth),
      ...headers,
    },
    body,
  });
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
  };
}

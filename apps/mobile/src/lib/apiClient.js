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
    chatWithListingAssistant({ conversation_id = null, messages = [], context = {} }, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: '/v1/listing-assistant/chat',
        method: 'POST',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conversation_id, messages, context }),
      });
    },
    chatWithAppAssistant({ messages = [], context = {} }, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: '/v1/app-assistant/chat',
        method: 'POST',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages, context }),
      });
    },
    getActiveListingAssistantConversation(auth = {}) {
      return requestJson({ apiBaseUrl, path: '/v1/listing-assistant/conversations/active', method: 'GET', auth });
    },
    updateListingAssistantConversation(conversationId, payload, auth = {}) {
      return requestJson({ apiBaseUrl, path: `/v1/listing-assistant/conversations/${encodeURIComponent(conversationId)}`, method: 'PATCH', auth, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    },
    trackExperience(event, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: '/v1/experience/events',
        method: 'POST',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(event),
      });
    },
    async classifyImageRoles({ images = [], category }, auth = {}) {
      const fd = new FormData();
      images.forEach((img, idx) => {
        fd.append('images', {
          uri: img.uri,
          name: img.fileName || `upload-${idx + 1}.jpg`,
          type: img.mimeType || 'image/jpeg',
        });
      });
      if (category) fd.append('category', category);
      return requestJson({
        apiBaseUrl,
        path: '/v1/images/classify-roles',
        method: 'POST',
        auth,
        body: fd,
      });
    },
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
    async uploadImages({ images = [], itemId = '', roleHints = [] }, auth = {}) {
      const fd = new FormData();
      images.forEach((img, idx) => {
        fd.append('images', {
          uri: img.uri,
          name: img.fileName || `upload-${idx + 1}.jpg`,
          type: img.mimeType || 'image/jpeg',
        });
      });
      if (itemId) fd.append('item_id', itemId);
      if (roleHints.length) fd.append('role_hints', JSON.stringify(roleHints));
      return requestJson({
        apiBaseUrl,
        path: '/v1/uploads/images',
        method: 'POST',
        auth,
        body: fd,
      });
    },
    async createImageUploadSlots({ images = [], itemId = '' }, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: '/v1/uploads/images/presign',
        method: 'POST',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          item_id: itemId || null,
          images: images.map((img, idx) => ({
            filename: img.filename || img.fileName || img.name || `upload-${idx + 1}.jpg`,
            content_type: img.contentType || img.mimeType || img.type || 'image/jpeg',
            content_length: Number.isFinite(Number(img.contentLength || img.fileSize || img.size)) ? Number(img.contentLength || img.fileSize || img.size) : null,
          })),
        }),
      });
    },
    async confirmImageUploads({ itemId, uploadedImages = [] }, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: '/v1/uploads/images/confirm',
        method: 'POST',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          item_id: itemId,
          uploaded_images: uploadedImages.map((img) => ({
            image_id: img.image_id || img.imageId,
            filename: img.filename || img.fileName || null,
            content_type: img.content_type || img.contentType || img.mimeType || 'image/jpeg',
            storage_uri: img.storage_uri || img.storageUri,
            role_hint: img.role_hint || img.roleHint || null,
            content_hash: img.content_hash || img.contentHash || null,
          })),
        }),
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
    getLatestListingAnalysisJob(listingId, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: `/v1/listings/${encodeURIComponent(listingId)}/analysis-jobs/latest`,
        method: 'GET',
        auth,
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
    createListingSupportRequest(listingId, payload, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: `/v1/listings/${encodeURIComponent(listingId)}/support-requests`,
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
    listMarketplace(limit = 50, auth = {}, options = {}) {
      const offset = Math.max(0, Number(options.offset || 0));
      return requestJson({
        apiBaseUrl,
        path: `/v1/listings?limit=${limit}&offset=${offset}&include_matches=true`,
        method: 'GET',
        auth,
      });
    },
    listMyListings(limit = 100, auth = {}, options = {}) {
      const offset = Math.max(0, Number(options.offset || 0));
      return requestJson({
        apiBaseUrl,
        path: `/v1/listings?mine=true&limit=${limit}&offset=${offset}`,
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
    actionOffer(offerId, status, receiveAddress = null, selectedOfferedListingId = null, auth = {}) {
      const selectedIsAuth = selectedOfferedListingId
        && typeof selectedOfferedListingId === 'object'
        && !Array.isArray(selectedOfferedListingId);
      const resolvedAuth = selectedIsAuth ? selectedOfferedListingId : auth;
      const resolvedSelectedId = selectedIsAuth ? null : selectedOfferedListingId;
      return requestJson({
        apiBaseUrl,
        path: `/v1/offers/${encodeURIComponent(offerId)}/action`,
        method: 'POST',
        auth: resolvedAuth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          status,
          receive_address: receiveAddress,
          selected_offered_listing_id: resolvedSelectedId || null,
        }),
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
    listNotifications(limit = 50, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: `/v1/me/notifications?limit=${limit}`,
        method: 'GET',
        auth,
      });
    },
    clearNotifications(auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: '/v1/me/notifications',
        method: 'DELETE',
        auth,
      });
    },
    deleteNotification(notificationId, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: `/v1/me/notifications/${encodeURIComponent(notificationId)}`,
        method: 'DELETE',
        auth,
      });
    },
    registerPushToken(payload, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: '/v1/me/push-token',
        method: 'POST',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload || {}),
      });
    },
    unregisterPushToken(token, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: '/v1/me/push-token',
        method: 'DELETE',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      });
    },
    likeListing(listingId, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: `/v1/listings/${encodeURIComponent(listingId)}/like`,
        method: 'POST',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
    },
    addressSuggestions({ q = '', city = '', state = '', postalCode = '', latitude = null, longitude = null } = {}, auth = {}) {
      const query = new URLSearchParams();
      if (q) query.set('q', q);
      if (city) query.set('city', city);
      if (state) query.set('state', state);
      if (postalCode) query.set('postal_code', postalCode);
      if (Number.isFinite(latitude)) query.set('latitude', String(latitude));
      if (Number.isFinite(longitude)) query.set('longitude', String(longitude));
      return requestJson({
        apiBaseUrl,
        path: `/v1/google/places/address-suggest?${query.toString()}`,
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
    cancelSubscription(auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: '/v1/me/subscription/cancel',
        method: 'POST',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cancel_at_period_end: true }),
      });
    },
    subscriptionAcknowledgments(auth = {}) {
      return requestJson({ apiBaseUrl, path: '/v1/me/subscription/acknowledgments', method: 'GET', auth });
    },
    createComplianceRequest(payload, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: '/v1/me/compliance-requests',
        method: 'POST',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload || {}),
      });
    },
    createTradeCase(offerId, payload, auth = {}) {
      return requestJson({
        apiBaseUrl,
        path: `/v1/offers/${encodeURIComponent(offerId)}/cases`,
        method: 'POST',
        auth,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload || {}),
      });
    },
  };
}

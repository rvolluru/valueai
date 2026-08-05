/**
 * @typedef {import("./types.js").ApiClientOptions} ApiClientOptions
 * @typedef {import("./types.js").AuthContext} AuthContext
 */

function normalizeBaseUrl(apiBaseUrl) {
  return String(apiBaseUrl || "").replace(/\/$/, "");
}

async function parseJsonOrNull(resp) {
  try {
    return await resp.json();
  } catch {
    return null;
  }
}

function detailFromPayload(payload) {
  if (!payload) return null;
  if (Array.isArray(payload.detail)) {
    return payload.detail[0]?.msg || payload.detail[0] || null;
  }
  return payload.detail || null;
}

export function buildAuthHeaders(auth = {}) {
  const bearer = (auth.bearerToken || "").trim();
  if (bearer) return { Authorization: `Bearer ${bearer}` };
  const apiKey = (auth.apiKey || "").trim();
  if (apiKey) return { "x-api-key": apiKey };
  return {};
}

export function resolveApiUrl(apiBaseUrl, path) {
  const base = normalizeBaseUrl(apiBaseUrl);
  if (!path.startsWith("/")) return `${base}/${path}`;
  return `${base}${path}`;
}

export async function requestJson({
  apiBaseUrl,
  path,
  method = "GET",
  auth = {},
  body,
  headers = {},
  fetchImpl = fetch,
}) {
  const requestHeaders = {
    ...buildAuthHeaders(auth),
    ...headers,
  };
  const url = resolveApiUrl(apiBaseUrl, path);
  const resp = await fetchImpl(url, { method, headers: requestHeaders, body });
  const payload = await parseJsonOrNull(resp);
  if (!resp.ok) {
    const detail = detailFromPayload(payload);
    const error = new Error(detail || `API error (${resp.status})`);
    error.status = resp.status;
    error.payload = payload;
    error.path = path;
    if (resp.status === 401 && typeof window !== "undefined" && typeof window.dispatchEvent === "function") {
      window.dispatchEvent(
        new CustomEvent("valueai:unauthorized", {
          detail: { status: resp.status, path },
        }),
      );
    }
    throw error;
  }
  return payload;
}

export async function requestFormData({
  apiBaseUrl,
  path,
  auth = {},
  formData,
  headers = {},
  fetchImpl = fetch,
}) {
  return requestJson({
    apiBaseUrl,
    path,
    method: "POST",
    auth,
    body: formData,
    headers,
    fetchImpl,
  });
}

/**
 * @param {ApiClientOptions} options
 */
export function createApiClient(options) {
  const apiBaseUrl = normalizeBaseUrl(options.apiBaseUrl);
  const fetchImpl = options.fetchImpl || fetch;
  const getBearerToken = options.getBearerToken;

  async function resolveAuth(auth = {}) {
    if (auth.bearerToken || auth.apiKey) return auth;
    if (!getBearerToken) return auth;
    const token = await getBearerToken();
    if (token && token.trim()) return { ...auth, bearerToken: token.trim() };
    return auth;
  }

  async function get(path, auth = {}) {
    const resolvedAuth = await resolveAuth(auth);
    return requestJson({ apiBaseUrl, path, auth: resolvedAuth, fetchImpl });
  }

  async function post(path, body, auth = {}, headers = {}) {
    const resolvedAuth = await resolveAuth(auth);
    return requestJson({
      apiBaseUrl,
      path,
      method: "POST",
      auth: resolvedAuth,
      fetchImpl,
      headers: {
        "Content-Type": "application/json",
        ...headers,
      },
      body: body == null ? undefined : JSON.stringify(body),
    });
  }

  async function patch(path, body, auth = {}) {
    const resolvedAuth = await resolveAuth(auth);
    return requestJson({
      apiBaseUrl,
      path,
      method: "PATCH",
      auth: resolvedAuth,
      fetchImpl,
      headers: { "Content-Type": "application/json" },
      body: body == null ? undefined : JSON.stringify(body),
    });
  }

  async function put(path, body, auth = {}) {
    const resolvedAuth = await resolveAuth(auth);
    return requestJson({
      apiBaseUrl,
      path,
      method: "PUT",
      auth: resolvedAuth,
      fetchImpl,
      headers: { "Content-Type": "application/json" },
      body: body == null ? undefined : JSON.stringify(body),
    });
  }

  async function del(path, auth = {}) {
    const resolvedAuth = await resolveAuth(auth);
    return requestJson({
      apiBaseUrl,
      path,
      method: "DELETE",
      auth: resolvedAuth,
      fetchImpl,
    });
  }

  async function analyzeItem({ images = [], category, userCondition, itemDescription, itemSize, debug = true }, auth = {}) {
    const resolvedAuth = await resolveAuth(auth);
    const fd = new FormData();
    images.forEach((img, idx) => {
      if (img?.uri && !img?.file) {
        fd.append("images", {
          uri: img.uri,
          name: img.fileName || `upload-${idx + 1}.jpg`,
          type: img.mimeType || "image/jpeg",
        });
        return;
      }
      fd.append("images", img.file || img);
    });
    if (category) fd.append("category", category);
    if (userCondition) fd.append("user_condition", userCondition);
    if (itemDescription) fd.append("item_description", itemDescription);
    if (itemSize) fd.append("item_size", itemSize);
    fd.append("debug", String(Boolean(debug)));
    return requestFormData({
      apiBaseUrl,
      path: "/v1/analyze",
      auth: resolvedAuth,
      formData: fd,
      fetchImpl,
    });
  }

  async function uploadImages({ images = [], itemId }, auth = {}) {
    const resolvedAuth = await resolveAuth(auth);
    const fd = new FormData();
    images.forEach((img, idx) => {
      if (img?.uri && !img?.file) {
        fd.append("images", {
          uri: img.uri,
          name: img.fileName || `upload-${idx + 1}.jpg`,
          type: img.mimeType || "image/jpeg",
        });
        return;
      }
      fd.append("images", img.file || img);
    });
    if (itemId) fd.append("item_id", itemId);
    return requestFormData({
      apiBaseUrl,
      path: "/v1/uploads/images",
      auth: resolvedAuth,
      formData: fd,
      fetchImpl,
    });
  }

  async function queueListingAnalysis(
    { listingId, images = [], category, userCondition, itemDescription, itemSize, debug = true },
    auth = {},
  ) {
    const resolvedAuth = await resolveAuth(auth);
    const fd = new FormData();
    images.forEach((img, idx) => {
      if (img?.uri && !img?.file) {
        fd.append("images", {
          uri: img.uri,
          name: img.fileName || `upload-${idx + 1}.jpg`,
          type: img.mimeType || "image/jpeg",
        });
        return;
      }
      fd.append("images", img.file || img);
    });
    if (category) fd.append("category", category);
    if (userCondition) fd.append("user_condition", userCondition);
    if (itemDescription) fd.append("item_description", itemDescription);
    if (itemSize) fd.append("item_size", itemSize);
    fd.append("debug", String(Boolean(debug)));
    return requestFormData({
      apiBaseUrl,
      path: `/v1/listings/${encodeURIComponent(listingId)}/analysis-jobs`,
      auth: resolvedAuth,
      formData: fd,
      fetchImpl,
    });
  }

  return {
    get,
    post,
    patch,
    put,
    delete: del,
    analyzeItem,
    uploadImages,
    queueListingAnalysis,
    listListings: (params = {}, auth = {}) => {
      const query = new URLSearchParams();
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== "") query.set(k, String(v));
      });
      const suffix = query.toString() ? `?${query.toString()}` : "";
      return get(`/v1/listings${suffix}`, auth);
    },
    createListing: (payload, auth = {}) => post("/v1/listings", payload, auth),
    updateListing: (listingId, payload, auth = {}) => put(`/v1/listings/${encodeURIComponent(listingId)}`, payload, auth),
    deleteListing: (listingId, auth = {}) => del(`/v1/listings/${encodeURIComponent(listingId)}`, auth),
    listMyListings: (limit = 100, auth = {}) => get(`/v1/listings?mine=true&limit=${limit}`, auth),
    listMarketplace: (limit = 50, auth = {}) => get(`/v1/listings?limit=${limit}&include_matches=true`, auth),
    listOfferCandidates: (listingId, limit = 100, auth = {}) =>
      get(`/v1/listings/${encodeURIComponent(listingId)}/offer-candidates?limit=${limit}`, auth),
    createOffer: (payload, auth = {}) => post("/v1/offers", payload, auth),
    incomingOffers: (status = "pending", limit = 50, auth = {}) =>
      get(`/v1/offers/incoming?status=${encodeURIComponent(status)}&limit=${limit}`, auth),
    offerAction: (offerId, status, receiveAddress = null, auth = {}) =>
      post(`/v1/offers/${encodeURIComponent(offerId)}/action`, { status, receive_address: receiveAddress }, auth),
    profileQuiz: (auth = {}) => get("/v1/me/profile-quiz", auth),
    saveProfileQuiz: (payload, auth = {}) => put("/v1/me/profile-quiz", payload, auth),
    clientState: (auth = {}) => get("/v1/me/client-state", auth),
    saveClientState: (payload, auth = {}) => put("/v1/me/client-state", payload, auth),
    paymentMethods: (auth = {}) => get("/v1/me/payment-methods", auth),
    createSetupCheckoutSession: ({ successUrl, cancelUrl }, auth = {}) =>
      post("/v1/me/payment-methods/stripe/setup-checkout-session", { success_url: successUrl, cancel_url: cancelUrl }, auth),
    syncStripePaymentMethods: (auth = {}) => post("/v1/me/payment-methods/stripe/sync", {}, auth),
  };
}

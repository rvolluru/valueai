import { createApiClient } from "../../../../packages/app-client/src/index.js";

let defaultBearerTokenProvider = null;

export function setWebBearerTokenProvider(provider) {
  defaultBearerTokenProvider = typeof provider === "function" ? provider : null;
}

export function createWebApiClient({ apiBaseUrl, apiKey = "", getBearerToken = null }) {
  const bearerTokenProvider = getBearerToken || defaultBearerTokenProvider;
  const client = createApiClient({
    apiBaseUrl,
    getBearerToken: bearerTokenProvider || undefined,
  });

  function authContext(bearerToken = "") {
    if (bearerToken && bearerToken.trim()) return { bearerToken: bearerToken.trim() };
    if (apiKey && apiKey.trim()) return { apiKey: apiKey.trim() };
    return {};
  }

  return {
    client,
    authContext,
  };
}

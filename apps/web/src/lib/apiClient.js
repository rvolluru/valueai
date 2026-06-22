import { createApiClient } from "../../../../packages/app-client/src/index.js";

export function createWebApiClient({ apiBaseUrl, apiKey = "", getBearerToken = null }) {
  const client = createApiClient({
    apiBaseUrl,
    getBearerToken: getBearerToken || undefined,
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

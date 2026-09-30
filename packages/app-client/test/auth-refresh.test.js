import assert from "node:assert/strict";
import test from "node:test";

import { requestJson } from "../src/index.js";

function response(status, payload) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  };
}

test("retries a bearer-authenticated 401 with a forced fresh token", async () => {
  const requests = [];
  const refreshOptions = [];
  const payload = await requestJson({
    apiBaseUrl: "https://api.example.test",
    path: "/v1/listings",
    auth: { bearerToken: "expired-token" },
    fetchImpl: async (_url, options) => {
      requests.push(options);
      return requests.length === 1
        ? response(401, { detail: "expired" })
        : response(200, { items: [] });
    },
    refreshBearerToken: async (options) => {
      refreshOptions.push(options);
      return "fresh-token";
    },
  });

  assert.deepEqual(payload, { items: [] });
  assert.equal(requests.length, 2);
  assert.equal(requests[0].headers.Authorization, "Bearer expired-token");
  assert.equal(requests[1].headers.Authorization, "Bearer fresh-token");
  assert.deepEqual(refreshOptions, [{ skipCache: true }]);
});

test("recovers when no cached bearer token was initially available", async () => {
  const requests = [];
  const payload = await requestJson({
    apiBaseUrl: "https://api.example.test",
    path: "/v1/listings",
    auth: {},
    fetchImpl: async (_url, options) => {
      requests.push(options);
      return requests.length === 1
        ? response(401, { detail: "missing token" })
        : response(200, { items: ["recovered"] });
    },
    refreshBearerToken: async ({ skipCache }) => skipCache ? "fresh-token" : null,
  });

  assert.deepEqual(payload, { items: ["recovered"] });
  assert.equal(requests.length, 2);
  assert.equal(requests[0].headers.Authorization, undefined);
  assert.equal(requests[1].headers.Authorization, "Bearer fresh-token");
});

test("emits unauthorized only after the refreshed token is rejected", async () => {
  const previousWindow = globalThis.window;
  const previousCustomEvent = globalThis.CustomEvent;
  const events = [];
  globalThis.CustomEvent = class CustomEvent {
    constructor(type, init) {
      this.type = type;
      this.detail = init?.detail;
    }
  };
  globalThis.window = {
    dispatchEvent(event) {
      events.push(event);
    },
  };

  try {
    await assert.rejects(
      requestJson({
        apiBaseUrl: "https://api.example.test",
        path: "/v1/me/profile",
        auth: { bearerToken: "expired-token" },
        fetchImpl: async () => response(401, { detail: "unauthorized" }),
        refreshBearerToken: async () => "refreshed-but-invalid-token",
      }),
      (error) => error.status === 401,
    );
    assert.equal(events.length, 1);
    assert.equal(events[0].type, "valueai:unauthorized");
    assert.deepEqual(events[0].detail, {
      status: 401,
      path: "/v1/me/profile",
      refreshAttempted: true,
    });
  } finally {
    globalThis.window = previousWindow;
    globalThis.CustomEvent = previousCustomEvent;
  }
});

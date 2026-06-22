/**
 * @typedef {Object} AuthContext
 * @property {string} [apiKey]
 * @property {string} [bearerToken]
 */

/**
 * @typedef {Object} Listing
 * @property {string} listing_id
 * @property {string} owner_subject
 * @property {string | null} title
 * @property {string | null} brand
 * @property {string | null} category
 * @property {string | null} condition
 * @property {number | null} estimated_value
 * @property {string | null} image
 * @property {string[]} [images]
 * @property {string | null} description
 * @property {string} [status]
 */

/**
 * @typedef {Object} ListingsResponse
 * @property {number} count
 * @property {Listing[]} items
 */

/**
 * @typedef {Object} AnalyzeResponse
 * @property {string} [category]
 * @property {Object} [item_profile]
 * @property {Object} [valuation]
 * @property {string | null} [debug_id]
 */

/**
 * @typedef {Object} ApiClientOptions
 * @property {string} apiBaseUrl
 * @property {typeof fetch} [fetchImpl]
 * @property {() => Promise<string>} [getBearerToken]
 */

export {};

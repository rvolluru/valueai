// Match thumbnails and expanded galleries use the same original image URLs.
export function matchPhotoUrls(item, apiBaseUrl) {
  return [...new Set([item?.image, ...(Array.isArray(item?.images) ? item.images : [])]
    .filter(url => typeof url === 'string' && url.trim())
    .map(url => { try { return new URL(url, apiBaseUrl).href; } catch { return null; } })
    .filter(Boolean))];
}

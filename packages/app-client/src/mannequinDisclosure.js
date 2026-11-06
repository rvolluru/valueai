export const MANNEQUIN_DISCLAIMER = 'AI-generated styling preview. Garment details, fit, and color may differ from the actual item. Refer to the original photos for accuracy. Additional styling items are not included.';

function imageKey(value) {
  if (typeof value !== 'string' || !value) return null;
  try { return new URL(value, 'https://www.jouft.com').pathname; } catch { return value; }
}

export function isMannequinImage(listing, src) {
  const key = imageKey(src);
  if (!key) return false;
  const assets = (listing?.analysis?.generated_assets || []).filter(asset =>
    asset?.synthetic && asset.review_decision !== 'exclude' && (!asset.kind || asset.kind.startsWith('mannequin')));
  const marked = (listing?.listed_images || listing?.listedImages || []).filter(image =>
    image?.role_hint === 'ai_mannequin' || (image?.synthetic && (!image.kind || image.kind.startsWith('mannequin'))));
  return [...(listing?.generatedImages || []), ...assets, ...marked].some(image =>
    [typeof image === 'string' ? image : null, image?.image_url, image?.d_img, image?.p_img]
      .some(url => imageKey(url) === key));
}

export function hasMannequinPreview(listing) {
  return Boolean(listing?.generatedImages?.length || listing?.analysis?.generated_assets?.some(asset => asset?.synthetic && asset.review_decision !== 'exclude')
    || (listing?.listed_images || listing?.listedImages || []).some(image => image?.role_hint === 'ai_mannequin' || image?.synthetic));
}

// Closet presentation only: leave persisted/public gallery ordering untouched.
export function closetCardImages(listing, originals = []) {
  const assets = listing?.analysis?.generated_assets || [];
  const excluded = new Set(assets.filter(asset => asset?.review_decision === 'exclude')
    .map(asset => imageKey(asset.image_url)));
  const candidates = [
    ...originals,
    ...(listing?.listedImages || listing?.listed_images || []).map(entry => entry?.d_img || entry?.p_img),
    ...(listing?.generatedImages || []).map(entry => typeof entry === 'string' ? entry : entry?.image_url),
    ...assets.map(asset => asset?.image_url),
  ].filter(src => typeof src === 'string' && src.trim() && !excluded.has(imageKey(src)));
  const mannequin = candidates.find(src => isMannequinImage(listing, src));
  return [...new Set([mannequin, ...originals].filter(Boolean))];
}

// Marketplace cards only promote previews already present in the public gallery.
export function marketplaceCardImages(listing, gallery = []) {
  const hidden = new Set((listing?.analysis?.generated_assets || [])
    .filter(asset => ['exclude', 'pending'].includes(asset?.review_decision))
    .map(asset => imageKey(asset.image_url)));
  const visible = gallery.filter(src => typeof src === 'string' && src.trim() && !hidden.has(imageKey(src)));
  const mannequin = visible.find(src => isMannequinImage(listing, src));
  return [...new Set([mannequin, ...visible].filter(Boolean))];
}

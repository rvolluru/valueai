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

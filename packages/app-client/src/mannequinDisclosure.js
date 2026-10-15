export const MANNEQUIN_DISCLAIMER = 'AI-generated styling preview. Garment details, fit, and color may differ from the actual item. Refer to the original photos for accuracy. Additional styling items are not included.';

export function hasMannequinPreview(listing) {
  return Boolean(listing?.generatedImages?.length || listing?.analysis?.generated_assets?.some(asset => asset?.synthetic && asset.review_decision !== 'exclude')
    || (listing?.listed_images || listing?.listedImages || []).some(image => image?.role_hint === 'ai_mannequin' || image?.synthetic));
}

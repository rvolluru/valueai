export const MAX_LISTING_PHOTOS = 6;

export function remainingPhotoSlots(existingCount = 0) {
  return Math.max(0, MAX_LISTING_PHOTOS - Math.max(0, existingCount));
}

export function appendListingPhotos(current, additions, savedPhotoCount = 0) {
  const available = remainingPhotoSlots(savedPhotoCount + current.length);
  return [...current, ...additions.filter((asset) => asset?.uri).slice(0, available)];
}

export function nextGalleryIndex(index, step, count) {
  return Math.max(0, Math.min(Math.max(0, count - 1), index + step));
}

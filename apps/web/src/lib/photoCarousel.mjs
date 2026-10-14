export function createPhotoCarousel({ src, alt, images = [] }) {
  const photos = images.filter(value => typeof value === 'string' && value);
  if (!photos.includes(src)) photos.unshift(src);
  const index = Math.max(0, photos.indexOf(src));
  return { src: photos[index], alt, images: photos, index };
}

export function movePhotoCarousel(current, step) {
  if (!current || current.images.length < 2) return current;
  const index = (current.index + step % current.images.length + current.images.length) % current.images.length;
  return { ...current, index, src: current.images[index] };
}

// The current gallery is authoritative; old analysis/media metadata must not
// discard additions, restore removals, or pair photos by a stale array index.
export function reconcileListingImages(imageUrls, previous = []) {
  return imageUrls.map((url, index) => {
    const existing = previous.find((entry) => entry?.d_img === url || entry?.p_img === url);
    return {
      p_img: existing?.p_img || url,
      d_img: url,
      is_hero: index === 0,
    };
  });
}

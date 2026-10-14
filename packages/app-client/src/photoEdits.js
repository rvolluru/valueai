export function cropPixels(width, height, crop) {
  const x = Math.max(0, Math.min(99, Number(crop.x) || 0));
  const y = Math.max(0, Math.min(99, Number(crop.y) || 0));
  const w = Math.max(1, Math.min(100 - x, Number(crop.width) || 100));
  const h = Math.max(1, Math.min(100 - y, Number(crop.height) || 100));
  const originX = Math.floor(width * x / 100);
  const originY = Math.floor(height * y / 100);
  return { originX, originY, width: Math.max(1, Math.min(width - originX, Math.round(width * w / 100))),
    height: Math.max(1, Math.min(height - originY, Math.round(height * h / 100))) };
}

from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image


def load_image(image_bytes: bytes) -> np.ndarray:
    return np.array(Image.open(io.BytesIO(image_bytes)).convert("RGB"))


class ProductCropper:
    def __init__(self, rembg_enabled: bool = False):
        self.rembg_enabled = rembg_enabled

    def crop(self, image_bytes: bytes) -> tuple[np.ndarray, dict]:
        rgb = load_image(image_bytes)
        if self.rembg_enabled:
            try:
                return self._crop_with_rembg(rgb)
            except Exception:
                pass
        return self._crop_by_background(rgb)

    def _crop_with_rembg(self, rgb: np.ndarray) -> tuple[np.ndarray, dict]:
        from rembg import remove  # type: ignore

        rgba = remove(rgb)
        alpha = rgba[:, :, 3]
        ys, xs = np.where(alpha > 10)
        if len(xs) == 0 or len(ys) == 0:
            return rgb, {"method": "rembg", "fallback": True}
        x1, x2 = int(xs.min()), int(xs.max())
        y1, y2 = int(ys.min()), int(ys.max())
        return rgb[y1 : y2 + 1, x1 : x2 + 1], {"method": "rembg", "bbox": [x1, y1, x2, y2]}

    def _crop_by_background(self, rgb: np.ndarray) -> tuple[np.ndarray, dict]:
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, thresh = cv2.threshold(blur, 245, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return rgb, {"method": "threshold_contour", "fallback": True}
        largest = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest)
        pad = 8
        x1, y1 = max(0, x - pad), max(0, y - pad)
        x2, y2 = min(rgb.shape[1], x + w + pad), min(rgb.shape[0], y + h + pad)
        return rgb[y1:y2, x1:x2], {"method": "threshold_contour", "bbox": [x1, y1, x2, y2]}

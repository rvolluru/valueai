from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image


def load_image_rgb(image_bytes: bytes) -> np.ndarray:
    pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return np.array(pil)


def preprocess_for_ocr(rgb: np.ndarray) -> tuple[np.ndarray, list[str]]:
    steps: list[str] = []
    img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    steps.append("grayscale")
    gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    steps.append("resize2x")
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    steps.append("clahe")
    gray = cv2.fastNlMeansDenoising(gray, h=10)
    steps.append("denoise")
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    gray = cv2.filter2D(gray, -1, kernel)
    steps.append("sharpen")
    return gray, steps

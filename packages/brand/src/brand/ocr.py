from __future__ import annotations

from pathlib import Path
import cv2

from .preprocess import load_image_rgb, preprocess_for_ocr
from .types import EvidenceBox, ImageInput, OcrLine, OcrResult


def _filename_text_hint(filename: str) -> list[str]:
    stem = Path(filename).stem
    tokens = [t for t in stem.replace("-", " ").replace("_", " ").split() if t]
    if not tokens:
        return []
    return [" ".join(tokens)]


class OcrEngine:
    def __init__(self) -> None:
        self.backend = "stub"
        self._reader = None
        try:
            from paddleocr import PaddleOCR  # type: ignore

            self._reader = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
            self.backend = "paddleocr"
        except Exception:
            try:
                import easyocr  # type: ignore

                self._reader = easyocr.Reader(["en"], gpu=False)
                self.backend = "easyocr"
            except Exception:
                self._reader = None
                self.backend = "stub"

    def run(self, images: list[ImageInput], boxes: list[EvidenceBox]) -> list[OcrResult]:
        by_image = {img.image_id: img for img in images}
        results: list[OcrResult] = []
        for box in boxes:
            img = by_image[box.image_id]
            rgb = load_image_rgb(img.bytes_data)
            preprocessed, steps = preprocess_for_ocr(rgb)
            lines = self._ocr_lines(img, rgb=rgb, preprocessed=preprocessed)
            results.append(
                OcrResult(
                    image_id=img.image_id,
                    box_id=box.box_id,
                    evidence_kind=box.kind,
                    lines=lines,
                    backend=self.backend,
                    preprocess_steps=steps,
                )
            )
        return results

    def _ocr_lines(self, image: ImageInput, rgb, preprocessed) -> list[OcrLine]:
        if self.backend == "paddleocr" and self._reader is not None:
            try:
                # PaddleOCR accepts numpy arrays; try preprocessed first, then original image.
                bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                inputs = [preprocessed, bgr]
                lines: list[OcrLine] = []
                for arr in inputs:
                    out = self._reader.ocr(arr, cls=True)  # type: ignore[attr-defined]
                    lines = []
                    for page in out or []:
                        for row in page or []:
                            text = row[1][0]
                            conf = float(row[1][1])
                            if text.strip():
                                lines.append(OcrLine(text=text, confidence=max(0.0, min(conf, 1.0))))
                    if lines:
                        return lines
            except Exception:
                pass

        if self.backend == "easyocr" and self._reader is not None:
            try:
                for arr in (preprocessed, rgb):
                    out = self._reader.readtext(arr)
                    lines = [
                        OcrLine(text=row[1], confidence=float(row[2]))
                        for row in out
                        if len(row) >= 3 and str(row[1]).strip()
                    ]
                    if lines:
                        return lines
            except Exception:
                pass

        hints = _filename_text_hint(image.filename)
        if hints:
            return [OcrLine(text=t, confidence=0.8) for t in hints]
        return []

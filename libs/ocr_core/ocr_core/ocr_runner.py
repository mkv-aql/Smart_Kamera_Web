# Smart_Kamera_Web/libs/ocr_core/ocr_core/ocr_runner.py
from __future__ import annotations
from typing import Protocol, Sequence

from .models import OCRItem, BBox
from .confidence import parse as parse_confidence


class OCRBackend(Protocol):
    """
    Minimal interface any OCR engine should implement.
    """
    def run(self, image_path: str) -> list[OCRItem]:
        ...


class EasyOCRBackend:
    """
    Adapter for your existing EasyOCR-based processor.
    We'll plug in your class_easyOCR_V1.OCRProcessor here.

    Expected OCRProcessor API:
      - ocr(image_path) -> pandas.DataFrame with columns:
            'bbox' (quad or xyxy), 'Namen', 'Confidence Level', 'Bildname'
    """
    def __init__(self, reader_lang: Sequence[str] = ("de", "en"), gpu: bool = False):
        # Defer import so the package installs without easyocr dependency if unused
        from importlib import import_module
        self._module = import_module("class_easyOCR_V1")  # adjust path if moved into libs later
        self._ocr = self._module.OCRProcessor(lang=reader_lang, gpu=gpu)

    def run(self, image_path: str) -> list[OCRItem]:
        import pandas as pd

        df = self._ocr.ocr(image_path)
        if not isinstance(df, pd.DataFrame) or df.empty:
            return []

        items: list[OCRItem] = []
        for _, row in df.iterrows():
            bbox_val = row.get("bbox")
            # Reuse CSV parsing logic to normalize bbox quickly:
            from .csv_adapter import _parse_bbox_cell  # local import to avoid cycles
            bbox = _parse_bbox_cell(bbox_val)
            if bbox is None:
                continue
            items.append(
                OCRItem(
                    bbox=bbox,
                    name=row.get("Namen") if pd.notna(row.get("Namen")) else None,
                    confidence=parse_confidence(row.get("Confidence Level")),
                )
            )
        return items

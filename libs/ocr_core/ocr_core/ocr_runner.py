# Smart_Kamera_Web/libs/ocr_core/ocr_core/ocr_runner.py
from __future__ import annotations
from typing import Protocol, Sequence

from .models import OCRItem
from .confidence import parse as parse_confidence

# Reuse the bbox parser already aware of your CSV/EasyOCR shapes
from .csv_adapter import _parse_bbox_cell  # local import; not exported


class OCRBackend(Protocol):
    def run(self, image_path: str) -> list[OCRItem]:
        ...


class EasyOCRBackend:
    """
    Adapter around your class_easyOCR_V1.OCRProcessor.

    Expected OCRProcessor API:
      - ocr(image_path) -> pandas.DataFrame with columns:
            'bbox', 'Namen', 'Confidence Level', 'Bildname'
    """
    def __init__(self, language: str = "de", gpu: bool = True, recog_network: str = "latin_g2"):
        # Lazy import so the package can install without easyocr if unused
        self._ocr = _load_ocr_processor()(language=language, gpu=gpu, recog_network=recog_network)

    def run(self, image_path: str) -> list[OCRItem]:
        import pandas as pd

        df = self._ocr.ocr(image_path)
        if not isinstance(df, pd.DataFrame) or df.empty:
            return []

        items: list[OCRItem] = []
        for _, row in df.iterrows():
            bbox = _parse_bbox_cell(row.get("bbox"))
            if bbox is None:
                continue
            name = row.get("Namen")
            conf = parse_confidence(row.get("Confidence Level"))
            items.append(
                OCRItem(
                    bbox=bbox,
                    name=str(name) if pd.notna(name) else None,
                    confidence=conf,
                )
            )
        return items


# def _load_ocr_processor():
#     """
#     Try vendor path first:
#       ocr_core.vendors.class_easyOCR_V1:OCRProcessor
#     Fallback to a top-level module named 'class_easyOCR_V1'.
#     """
#     from importlib import import_module
#
#     # 1) vendor path inside the package
#     try:
#         mod = import_module("ocr_core.vendors.class_easyOCR_V1")
#         return getattr(mod, "OCRProcessor")
#     except Exception:
#         pass
#
#     # 2) top-level module in the repo
#     mod = import_module("class_easyOCR_V1")
#     return getattr(mod, "OCRProcessor")

# Replace the whole _load_ocr_processor() with this:
def _load_ocr_processor():
    """
    Try these in order:
      1) ocr_core.vendors.class_easyOCR_V1   (if you vendor the file)
      2) Modules.class_easyOCR_V1            (original desktop layout)
      3) class_easyOCR_V1                    (file at project root)
    """
    from importlib import import_module

    for modname in (
        "ocr_core.vendors.class_easyOCR_V1",
        "Modules.class_easyOCR_V1",
        "class_easyOCR_V1",
    ):
        try:
            mod = import_module(modname)
            return getattr(mod, "OCRProcessor")
        except Exception:
            continue

    # If we get here, nothing worked:
    raise ImportError(
        "Could not import OCRProcessor. Tried: "
        "ocr_core.vendors.class_easyOCR_V1, Modules.class_easyOCR_V1, class_easyOCR_V1"
    )


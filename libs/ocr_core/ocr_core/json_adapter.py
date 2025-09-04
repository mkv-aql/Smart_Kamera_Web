# Smart_Kamera_Web/libs/ocr_core/ocr_core/json_adapter.py
from __future__ import annotations
from typing import Iterable

from .models import BBox, OCRItem
from .confidence import parse as parse_confidence


def to_json(items: Iterable[OCRItem]) -> list[dict]:
    return [
        {
            "bbox": {"x1": it.bbox.x1, "y1": it.bbox.y1, "x2": it.bbox.x2, "y2": it.bbox.y2},
            "name": it.name,
            "confidence": it.confidence,
            "status": it.status,
            "image_id": it.image_id,
        }
        for it in items
    ]


def from_json(payload: list[dict]) -> list[OCRItem]:
    out: list[OCRItem] = []
    for d in payload or []:
        b = d.get("bbox") or {}
        bbox = BBox(x1=int(b["x1"]), y1=int(b["y1"]), x2=int(b["x2"]), y2=int(b["y2"]))
        out.append(
            OCRItem(
                bbox=bbox,
                name=d.get("name"),
                confidence=parse_confidence(d.get("confidence")),
                status=d.get("status", "active"),
                image_id=d.get("image_id"),
            )
        )
    return out

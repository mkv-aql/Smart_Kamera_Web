# Smart_Kamera_Web/libs/ocr_core/ocr_core/csv_adapter.py
from __future__ import annotations
import csv
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from .models import BBox, OCRItem
from .confidence import parse as parse_confidence


CSV_HEADER = ["bbox", "Namen", "Confidence Level", "Bildname"]


def _parse_bbox_cell(cell: str | list | dict) -> BBox | None:
    """
    Accepts either:
      - EasyOCR quad string: '[[x0,y0],[x1,y1],[x2,y2],[x3,y3]]'
      - XYXY list string:    '[x1,y1,x2,y2]'
      - already-parsed list/dict
    Returns a normalized BBox or None on failure.
    """
    if cell is None:
        return None
    val = cell
    if isinstance(val, str):
        val = val.strip()
        # Try JSON first (safer than ast.literal_eval)
        try:
            val = json.loads(val)
        except Exception:
            # fall back: attempt to coerce simple CSV-like '[1,2,3,4]'
            try:
                val = eval(val, {"__builtins__": {}})  # last resort; callers trust their own CSV
            except Exception:
                return None

    # Quad → bbox
    if isinstance(val, (list, tuple)) and len(val) == 4 and isinstance(val[0], (list, tuple)):
        return BBox.from_quad(val)

    # XYXY list
    if isinstance(val, (list, tuple)) and len(val) == 4:
        x1, y1, x2, y2 = [int(round(float(x))) for x in val]
        return BBox(x1=x1, y1=y1, x2=x2, y2=y2)

    # Dict with keys
    if isinstance(val, dict) and {"x1","y1","x2","y2"} <= set(val.keys()):
        return BBox(x1=int(val["x1"]), y1=int(val["y1"]), x2=int(val["x2"]), y2=int(val["y2"]))

    return None


def load_csv(path: str | Path) -> list[OCRItem]:
    """
    Load your current CSV format into normalized OCRItem list.
    Expects header: ['bbox','Namen','Confidence Level','Bildname']
    """
    p = Path(path)
    if not p.exists():
        return []

    df = pd.read_csv(p)
    items: list[OCRItem] = []
    for _, row in df.iterrows():
        bbox = _parse_bbox_cell(row.get("bbox"))
        if bbox is None:
            continue
        name = row.get("Namen")
        conf = parse_confidence(row.get("Confidence Level"))
        items.append(OCRItem(bbox=bbox, name=name if pd.notna(name) else None, confidence=conf))
    return items


def save_csv(path: str | Path, items: Iterable[OCRItem], bildname: str | None = None) -> None:
    """
    Persist items back to the GUI-compatible CSV format.
    - bbox is stored as an EasyOCR-like quad JSON for compatibility, or as xyxy list.
      Here we store XYXY for simplicity.
    - 'Bildname' can be passed, otherwise left empty.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for it in items:
        rows.append({
            "bbox": json.dumps([it.bbox.x1, it.bbox.y1, it.bbox.x2, it.bbox.y2]),
            "Namen": it.name or "",
            "Confidence Level": f"{int(round(it.confidence*100))}%" if it.confidence is not None else "",
            "Bildname": bildname or "",
        })

    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

# Smart_Kamera_Web/libs/ocr_core/ocr_core/bbox_utils.py
from __future__ import annotations
from .models import BBox

def contains_point(b: BBox, x: int, y: int) -> bool:
    """Return True if (x,y) is inside b (inclusive edges)."""
    return (b.x1 <= x <= b.x2) and (b.y1 <= y <= b.y2)

def area(b: BBox) -> int:
    """Area in pixels (0 if degenerate)."""
    w = max(0, b.x2 - b.x1)
    h = max(0, b.y2 - b.y1)
    return w * h

def intersect(a: BBox, b: BBox) -> BBox | None:
    """Intersection box (or None if no overlap)."""
    x1 = max(a.x1, b.x1)
    y1 = max(a.y1, b.y1)
    x2 = min(a.x2, b.x2)
    y2 = min(a.y2, b.y2)
    if x2 <= x1 or y2 <= y1:
        return None
    return BBox(x1=x1, y1=y1, x2=x2, y2=y2)

def iou(a: BBox, b: BBox) -> float:
    """Intersection-over-Union in [0,1]."""
    inter = intersect(a, b)
    if inter is None:
        return 0.0
    ai = area(inter)
    return ai / float(area(a) + area(b) - ai) if (area(a) + area(b) - ai) > 0 else 0.0

def scale(b: BBox, sx: float, sy: float) -> BBox:
    """Scale a bbox by factors sx, sy around the origin."""
    return BBox(
        x1=int(round(b.x1 * sx)),
        y1=int(round(b.y1 * sy)),
        x2=int(round(b.x2 * sx)),
        y2=int(round(b.y2 * sy)),
    )

def translate(b: BBox, dx: int, dy: int) -> BBox:
    """Shift a bbox by dx, dy."""
    return BBox(x1=b.x1 + dx, y1=b.y1 + dy, x2=b.x2 + dx, y2=b.y2 + dy)

def clip(b: BBox, width: int, height: int) -> BBox:
    """Clip bbox to image bounds [0,width) x [0,height)."""
    x1 = min(max(b.x1, 0), max(0, width - 1))
    y1 = min(max(b.y1, 0), max(0, height - 1))
    x2 = min(max(b.x2, 0), max(0, width - 1))
    y2 = min(max(b.y2, 0), max(0, height - 1))
    return BBox(x1=min(x1, x2), y1=min(y1, y2), x2=max(x1, x2), y2=max(y1, y2))

# Smart_Kamera_Web/libs/ocr_core/ocr_core/confidence.py
from __future__ import annotations

def parse(val: str | float | int | None) -> float | None:
    """
    Normalize confidence to [0,1].

    Accepted forms:
      - "87%" -> 0.87
      - 87    -> 0.87
      - 0.87  -> 0.87
      - None/invalid -> None
    """
    if val is None:
        return None
    try:
        s = str(val).strip()
        if s.endswith("%"):
            return _clip(float(s[:-1]) / 100.0)
        f = float(s)
        if f > 1.0:
            return _clip(f / 100.0)
        return _clip(f)
    except Exception:
        return None


def _clip(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


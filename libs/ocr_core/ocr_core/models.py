# Smart_Kamera_Web/libs/ocr_core/ocr_core/models.py
from __future__ import annotations
from typing import Literal, Iterable
from pydantic import BaseModel, Field, model_validator


class BBox(BaseModel):
    """
    Axis-aligned bounding box in pixel coords (top-left -> bottom-right).

    (x1, y1) ----
       |        |
       |        |
       ---- (x2, y2)

    All values are inclusive integers in image space.
    """
    x1: int = Field(..., description="Left")
    y1: int = Field(..., description="Top")
    x2: int = Field(..., description="Right")
    y2: int = Field(..., description="Bottom")

    @model_validator(mode="after")
    def _validate_order(self) -> "BBox":
        if self.x2 < self.x1 or self.y2 < self.y1:
            # normalize by swapping if needed
            x1, x2 = sorted((self.x1, self.x2))
            y1, y2 = sorted((self.y1, self.y2))
            object.__setattr__(self, "x1", x1)
            object.__setattr__(self, "x2", x2)
            object.__setattr__(self, "y1", y1)
            object.__setattr__(self, "y2", y2)
        return self

    @classmethod
    def from_list(cls, xyxy: Iterable[int]) -> "BBox":
        x1, y1, x2, y2 = list(xyxy)
        return cls(x1=x1, y1=y1, x2=x2, y2=y2)

    @classmethod
    def from_quad(cls, quad: Iterable[Iterable[float]]) -> "BBox":
        """
        Build from a 4-point polygon (the EasyOCR-style bbox):
        e.g. [[x0,y0],[x1,y1],[x2,y2],[x3,y3]]
        """
        pts = list(quad)
        xs = [int(round(p[0])) for p in pts]
        ys = [int(round(p[1])) for p in pts]
        return cls(x1=min(xs), y1=min(ys), x2=max(xs), y2=max(ys))

    def width(self) -> int:
        return max(0, self.x2 - self.x1)

    def height(self) -> int:
        return max(0, self.y2 - self.y1)

    def to_list(self) -> list[int]:
        return [self.x1, self.y1, self.x2, self.y2]


class OCRItem(BaseModel):
    """
    One OCR detection row, normalized for storage / transport.
    """
    bbox: BBox
    name: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    status: Literal["active", "removed"] = "active"
    image_id: str | None = None  # optional link to an image row in DB

    def is_low_conf(self, threshold: float = 0.6) -> bool:
        return (self.confidence is not None) and (self.confidence < threshold)


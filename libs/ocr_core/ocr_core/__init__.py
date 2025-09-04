# Smart_Kamera_Web/libs/ocr_core/ocr_core/__init__.py
from .models import BBox, OCRItem
from .confidence import parse as parse_confidence
from .bbox_utils import contains_point, area, intersect, iou, scale, translate, clip

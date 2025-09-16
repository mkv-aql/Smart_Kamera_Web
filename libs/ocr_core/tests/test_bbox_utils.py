from ocr_core.models import BBox
from ocr_core import bbox_utils

def test_contains_point():
    b = BBox(x1=0, y1=0, x2=10, y2=10)
    assert bbox_utils.contains_point(b, 5, 5)
    assert not bbox_utils.contains_point(b, 20, 20)

def test_iou():
    a = BBox(x1=0, y1=0, x2=10, y2=10)
    b = BBox(x1=5, y1=5, x2=15, y2=15)
    i = bbox_utils.iou(a, b)
    assert 0 < i < 1

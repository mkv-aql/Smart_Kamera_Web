import tempfile
from pathlib import Path

from ocr_core.csv_adapter import save_csv, load_csv
# from libs.ocr_core.ocr_core.csv_adapter import save_csv, load_csv
from ocr_core.models import BBox, OCRItem

def test_roundtrip_csv(tmp_path: Path):
    items = [
        OCRItem(bbox=BBox(x1=0,y1=0,x2=10,y2=10), name="Test", confidence=0.9)
    ]
    f = tmp_path / "out.csv"
    save_csv(f, items, bildname="demo")
    loaded = load_csv(f)
    assert len(loaded) == 1
    assert loaded[0].name == "Test"
    assert abs(loaded[0].confidence - 0.9) < 1e-6

import types
import pandas as pd

from ocr_core.ocr_runner import EasyOCRBackend, _load_ocr_processor

class FakeOCR:
    def __init__(self, **kwargs): ...
    def ocr(self, image_path: str):
        return pd.DataFrame([
            {"bbox": [[0,0],[10,0],[10,10],[0,10]], "Namen":"Test", "Confidence Level":"87%", "Bildname":"img"}
        ])

def test_easyocr_adapter_monkeypatch(monkeypatch):
    monkeypatch.setattr("ocr_core.ocr_runner._load_ocr_processor", lambda: lambda **kw: FakeOCR(**kw))
    backend = EasyOCRBackend(language="de", gpu=False)
    items = backend.run("dummy.jpg")
    assert len(items) == 1
    assert items[0].name == "Test"
    assert 0.86 < (items[0].confidence or 0) < 0.88

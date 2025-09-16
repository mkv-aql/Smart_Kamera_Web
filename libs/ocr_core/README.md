
models.py          # Pydantic (or dataclass) types: BBox, OCRItem, etc.

bbox_utils.py      # scaling, contains_point, IoU, clipping

confidence.py      # parse/normalize confidence

csv_adapter.py     # CSV <-> list[OCRItem]

json_adapter.py    # JSON <-> list[OCRItem]

ocr_runner.py      # wrapper around EasyOCR (or your OCRProcessor)

storage.py         # storage interface + local FS impl


## Install the lcoal libraries:
cd in root of Smart_Kamera_Web
```
pip install -e libs/ocr_core

or

python -m pip install -e libs/ocr_core

```

Verify import is working
```
from ocr_core import OCRItem, BBox, parse_confidence

```


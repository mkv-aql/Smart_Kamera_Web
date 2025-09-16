# backend/app_local.py
# Run from PyCharm (or terminal): uvicorn backend.app_local:app --reload

# --- PATH SHIM: ensure project + libs are importable in PyCharm/Windows ---
import sys
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]  # .../Smart_Kamera_Web
sys.path.insert(0, str(ROOT))                        # for class_easyOCR_V1 / Modules.class_easyOCR_V1 if needed
sys.path.insert(0, str(ROOT / "libs" / "ocr_core"))  # so 'import ocr_core' works even if not installed
# --- END PATH SHIM ---

import os
import io
import json
import zipfile
import threading
import queue
from uuid import uuid4
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ocr_core.ocr_runner import EasyOCRBackend
from ocr_core.json_adapter import to_json
from ocr_core.csv_adapter import save_csv

# -----------------------------------------------------------------------------
# Storage (filesystem)
# -----------------------------------------------------------------------------
DATA_DIR = Path(os.getenv("DATA_DIR", "./data")).resolve()
IMAGES_DIR = DATA_DIR / "images"
RESULTS_DIR = DATA_DIR / "results"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

class LocalStorage:
    def __init__(self, root: Path):
        self.root = Path(root)
    def put(self, key: str, data: bytes) -> None:
        p = self.root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    def get_path(self, key: str) -> Path:
        return self.root / key

storage = LocalStorage(IMAGES_DIR)

# -----------------------------------------------------------------------------
# In-process job queue + worker thread
# -----------------------------------------------------------------------------
job_q: "queue.Queue[dict]" = queue.Queue()
job_status: Dict[str, str] = {}            # job_id -> queued|running|done|error
image_key_by_id: Dict[str, str] = {}       # image_id -> stored key

# serialize writes to results files (worker + API calls)
results_lock = threading.Lock()

# Use CPU by default for portability; flip to True later if you have GPU/Torch.
ocr = EasyOCRBackend(language="de", gpu=False)

def _results_path(image_id: str) -> Path:
    return RESULTS_DIR / f"{image_id}.json"

def _load_results(image_id: str) -> dict:
    p = _results_path(image_id)
    if not p.exists():
        return {"items": []}
    return json.loads(p.read_text(encoding="utf-8"))

def _save_results(image_id: str, data: dict) -> None:
    _results_path(image_id).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

def _write_csv_filtered(image_id: str, items: list[dict]) -> None:
    """
    Write CSV excluding items with status == 'removed'.
    """
    from ocr_core.models import OCRItem, BBox
    active: list[OCRItem] = []
    for it in items:
        if it.get("status") == "removed":
            continue
        b = it["bbox"]
        active.append(
            OCRItem(
                bbox=BBox(x1=b["x1"], y1=b["y1"], x2=b["x2"], y2=b["y2"]),
                name=it.get("name"),
                confidence=it.get("confidence"),
                image_id=image_id,
            )
        )
    save_csv(RESULTS_DIR / f"{image_id}.csv", active, bildname=image_id)

def worker_loop():
    while True:
        job = job_q.get()  # blocks
        if job is None:
            break
        job_id = job["job_id"]
        image_id = job["image_id"]
        key = image_key_by_id.get(image_id)

        if not key:
            job_status[job_id] = "error"
            job_q.task_done()
            continue

        try:
            job_status[job_id] = "running"
            image_path = storage.get_path(key)
            items = ocr.run(str(image_path))  # list[OCRItem]
            json_out = {"items": to_json(items)}

            with results_lock:
                # write JSON
                (RESULTS_DIR / f"{image_id}.json").write_text(
                    json.dumps(json_out, ensure_ascii=False), encoding="utf-8"
                )
                # write CSV (all items are active initially)
                save_csv(RESULTS_DIR / f"{image_id}.csv", items, bildname=image_id)

            job_status[job_id] = "done"
        except Exception:
            job_status[job_id] = "error"
        finally:
            job_q.task_done()

threading.Thread(target=worker_loop, daemon=True).start()

# -----------------------------------------------------------------------------
# FastAPI app + static UI
# -----------------------------------------------------------------------------
app = FastAPI(title="Smart_Kamera_Web (local, no Docker)", version="0.1.0")

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/ui", StaticFiles(directory=STATIC_DIR, html=True), name="ui")

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/ui")

# -----------------------------------------------------------------------------
# Schemas
# -----------------------------------------------------------------------------
class UploadResp(BaseModel):
    image_id: str
    filename: str

class JobResp(BaseModel):
    job_id: str

class BatchReq(BaseModel):
    image_ids: Optional[List[str]] = None

class BatchResp(BaseModel):
    job_ids: List[str]

# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/images")
def list_images():
    out = []
    for image_id, key in image_key_by_id.items():
        filename = key.split("_", 1)[1] if "_" in key else key
        out.append({"image_id": image_id, "filename": filename})
    return {"items": out}

@app.get("/images/{image_id}/file")
def get_image_file(image_id: str):
    key = image_key_by_id.get(image_id)
    if not key:
        raise HTTPException(404, "image_id not found")
    p = storage.get_path(key)
    if not p.exists():
        raise HTTPException(404, "file not found on disk")
    return FileResponse(p)

@app.post("/images", response_model=UploadResp)
async def upload_image(file: UploadFile = File(...)):
    """
    Upload a single image.
    """
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    image_id = str(uuid4())
    key = f"{image_id}_{file.filename}"
    storage.put(key, data)
    image_key_by_id[image_id] = key
    return UploadResp(image_id=image_id, filename=file.filename)

@app.post("/images/batch")
async def upload_images_batch(files: List[UploadFile] = File(...)):
    """
    Upload multiple images in one request.
    Returns: {"items":[{"image_id","filename"}, ...]}
    """
    items = []
    for f in files:
        data = await f.read()
        if not data:
            continue
        image_id = str(uuid4())
        key = f"{image_id}_{f.filename}"
        storage.put(key, data)
        image_key_by_id[image_id] = key
        items.append({"image_id": image_id, "filename": f.filename})
    return {"items": items}

@app.post("/ocr/jobs", response_model=JobResp)
def create_ocr_job(image_id: str):
    if image_id not in image_key_by_id:
        raise HTTPException(404, "image_id not found")
    job_id = str(uuid4())
    job_status[job_id] = "queued"
    job_q.put({"job_id": job_id, "image_id": image_id})
    return JobResp(job_id=job_id)

@app.post("/ocr/jobs/batch", response_model=BatchResp)
def create_ocr_jobs_batch(req: BatchReq):
    ids = req.image_ids or list(image_key_by_id.keys())
    job_ids: list[str] = []
    for image_id in ids:
        if image_id not in image_key_by_id:
            continue
        job_id = str(uuid4())
        job_status[job_id] = "queued"
        job_q.put({"job_id": job_id, "image_id": image_id})
        job_ids.append(job_id)
    return BatchResp(job_ids=job_ids)

@app.get("/ocr/jobs/{job_id}")
def job_state(job_id: str):
    return {"job_id": job_id, "status": job_status.get(job_id, "unknown")}

@app.get("/images/{image_id}/results")
def get_results(image_id: str):
    p = RESULTS_DIR / f"{image_id}.json"
    if not p.exists():
        raise HTTPException(404, "no results for this image")
    return json.loads(p.read_text(encoding="utf-8"))

@app.get("/images/{image_id}/export.csv")
def export_csv(image_id: str):
    # Always re-write CSV from the latest JSON, filtering removed entries
    with results_lock:
        data = _load_results(image_id)
        items = data.get("items", [])
        _write_csv_filtered(image_id, items)
        p = RESULTS_DIR / f"{image_id}.csv"
        if not p.exists():
            raise HTTPException(404, "no CSV for this image")
    return FileResponse(p, media_type="text/csv", filename=f"{image_id}.csv")

@app.get("/exports/results.zip")
def download_all_csv_zip():
    """
    Bundle all CSVs in results/ as a single ZIP.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in RESULTS_DIR.glob("*.csv"):
            z.write(p, arcname=p.name)
    buf.seek(0)
    headers = {"Content-Disposition": "attachment; filename=results_csv.zip"}
    return StreamingResponse(buf, media_type="application/zip", headers=headers)

@app.patch("/images/{image_id}/results/{index}")
def patch_result(image_id: str, index: int, payload: dict = Body(...)):
    with results_lock:
        data = _load_results(image_id)
        items = data.get("items", [])
        if not (0 <= index < len(items)):
            raise HTTPException(404, "result index out of range")
        item = items[index]
        if "name" in payload:
            item["name"] = payload["name"]
        if "status" in payload:
            item["status"] = payload["status"]
        items[index] = item
        data["items"] = items
        _save_results(image_id, data)
        _write_csv_filtered(image_id, items)
    return {"ok": True, "item": item}

@app.post("/images/{image_id}/results/{index}/remove")
def remove_result(image_id: str, index: int):
    with results_lock:
        data = _load_results(image_id)
        items = data.get("items", [])
        if not (0 <= index < len(items)):
            raise HTTPException(404, "result index out of range")
        items[index]["status"] = "removed"
        data["items"] = items
        _save_results(image_id, data)
        _write_csv_filtered(image_id, items)
    return {"ok": True}

# Optional: allow running this file directly via "Run"
if __name__ == "__main__":
    import uvicorn
    os.environ.setdefault("DATA_DIR", "./data")
    uvicorn.run("backend.app_local:app", host="127.0.0.1", port=8000, reload=True)

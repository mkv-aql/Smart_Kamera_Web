# backend/app_local.py
# Run: uvicorn backend.app_local:app --reload

# --- PATH SHIM (Windows/PyCharm) ---
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "libs" / "ocr_core"))
# --- end shim ---

import os, io, json, zipfile, threading, queue
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
# Storage
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
# Jobs + OCR
# -----------------------------------------------------------------------------
job_q: "queue.Queue[dict]" = queue.Queue()
job_status: Dict[str, str] = {}
image_key_by_id: Dict[str, str] = {}
results_lock = threading.Lock()

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
    """Write CSV for active items (exclude status=='removed')."""
    from ocr_core.models import OCRItem, BBox
    active = []
    for it in items:
        if it.get("status") == "removed":
            continue
        b = it["bbox"]
        active.append(
            OCRItem(
                bbox=BBox(x1=int(round(b["x1"])), y1=int(round(b["y1"])),
                          x2=int(round(b["x2"])), y2=int(round(b["y2"]))),
                name=it.get("name"),
                confidence=it.get("confidence"),
                image_id=image_id,
            )
        )
    save_csv(RESULTS_DIR / f"{image_id}.csv", active, bildname=image_id)

def worker_loop():
    while True:
        job = job_q.get()
        if job is None:
            break
        job_id = job["job_id"]
        image_id = job["image_id"]
        key = image_key_by_id.get(image_id)
        try:
            job_status[job_id] = "running"
            image_path = storage.get_path(key)
            items = ocr.run(str(image_path))            # list[OCRItem]
            json_out = {"items": to_json(items)}        # list[dict]
            with results_lock:
                (_results_path(image_id)).write_text(json.dumps(json_out, ensure_ascii=False), encoding="utf-8")
                save_csv(RESULTS_DIR / f"{image_id}.csv", items, bildname=image_id)
            job_status[job_id] = "done"
        except Exception:
            job_status[job_id] = "error"
        finally:
            job_q.task_done()

threading.Thread(target=worker_loop, daemon=True).start()

# -----------------------------------------------------------------------------
# FastAPI + static UI
# -----------------------------------------------------------------------------
app = FastAPI(title="Smart_Kamera_Web (local, no Docker)", version="0.2.0")
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
# Cleaner (pure Python; operates on list[dict] items)
# Order: split -> normalize/titlecase -> spelling -> blacklist -> strip digits/specials
#        -> drop short (<=2 letters) -> coerce bbox ints -> reorder (top-left)
# -----------------------------------------------------------------------------
import re
from typing import List

# keep/extend as needed
BLACKLIST = {
    'nein','Reklame','REKLAME','Werbung','WERBUNG','Anzeige','ANZEIGE',
    'einwerfen','Einwurf','Bitte','bitte','GmbH','danke','Danke','Danke!',
    'keine','Keine','kein','Kein','keine Werbung','Keine Werbung','keine Reklame',
    'Keine Reklame','werbung','Rewe','Vorsicht','Hund','Haus','Büro','Privat',
    'Öffnungszeiten','Vielen','Dank','SIEDLE','Siedle','Ritto','Elcom','service','Www'
}

SPELLING = {
    'Muller':'Müller','Schmltt':'Schmitt','Schmldt':'Schmidt','Jager':'Jäger',
    'Schafer':'Schäfer','Schmilz':'Schmitz','Konig':'König','Schonwald':'Schönwald',
    'Schlafer':'Schläfer'
}

SPLIT_DELIMS = ("&","/","-")

# letters incl. diacritics; allow spaces only
_RE_ONLY_LETTERS_AND_SPACES = re.compile(r"[^A-Za-zÀ-ÖØ-öø-ÿ\s]+")

def _titlecase_if_upper(s: str) -> str:
    return s.title() if s.isupper() else s

def _contains_blacklist(s: str) -> bool:
    # match substring occurrence
    return any(w in s for w in BLACKLIST)

def _split_name(name: str) -> List[str]:
    parts = [name]
    for d in SPLIT_DELIMS:
        parts = sum((p.split(d) for p in parts), [])
    # trim empties
    return [p.strip() for p in parts if p and p.strip()]

def _strip_specials_and_digits(s: str) -> str:
    # if ANY digit present, we drop the item entirely (handled in clean_items)
    # here we strip all non-letters/spaces (punctuation etc.)
    s2 = _RE_ONLY_LETTERS_AND_SPACES.sub("", s)
    # collapse multiple spaces
    s2 = re.sub(r"\s+", " ", s2).strip()
    return s2

def _has_digit(s: str) -> bool:
    return any(ch.isdigit() for ch in s)

def _coerce_bbox_int(b: dict) -> dict:
    return {
        "x1": int(round(b["x1"])),
        "y1": int(round(b["y1"])),
        "x2": int(round(b["x2"])),
        "y2": int(round(b["y2"])),
    }

# keep your helpers/regex/constants; replace clean_items with this:

def clean_items(items: List[dict]) -> List[dict]:
    """
    New behavior:
      - Remove digits and punctuation; keep only letters+spaces.
      - If result has no letters (numbers-only) -> drop.
      - If letters-only length <= 2 -> drop.
      - Still: split -> normalize/titlecase -> spelling -> blacklist -> clean -> coerce bbox -> reorder.
    """
    active = [it for it in items if it.get("status") != "removed"]

    kept: List[dict] = []
    for it in active:
        raw_name = (it.get("name") or "").strip()
        if not raw_name:
            continue

        parts = _split_name(raw_name) or [raw_name]
        for p in parts:
            # normalize + titlecase if ALLCAPS
            p = _titlecase_if_upper(p.strip())

            # spelling fixes
            if p in SPELLING:
                p = SPELLING[p]

            # blacklist drop early
            if _contains_blacklist(p):
                continue

            # strip digits + punctuation; keep letters+spaces only
            p_clean = _strip_specials_and_digits(p)

            # must contain at least one letter (i.e., not numbers-only or empty)
            if not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", p_clean):
                continue

            # drop if <= 2 letters after cleaning (ignore spaces)
            letter_count = len(re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ]", "", p_clean))
            if letter_count <= 2:
                continue

            kept.append({
                "bbox": _coerce_bbox_int(it["bbox"]),
                "name": p_clean,
                "confidence": it.get("confidence"),
                "status": "active",
            })

    # dedupe by (bbox, name) keeping higher confidence
    dedup = {}
    for k in kept:
        key = (k["bbox"]["x1"], k["bbox"]["y1"], k["bbox"]["x2"], k["bbox"]["y2"], k["name"])
        if key not in dedup or (k.get("confidence") or 0) > (dedup[key].get("confidence") or 0):
            dedup[key] = k

    kept = list(dedup.values())
    kept.sort(key=lambda it: (it["bbox"]["y1"], it["bbox"]["x1"]))
    return kept



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

@app.post("/images/{image_id}/clean")
def clean_results(image_id: str):
    """Clean current results: rewrite JSON to cleaned active items and refresh CSV."""
    with results_lock:
        data = _load_results(image_id)
        items = data.get("items", [])
        cleaned = clean_items(items)          # << run cleaner (active only)
        new_payload = {"items": cleaned}      # replace with cleaned set
        _save_results(image_id, new_payload)
        _write_csv_filtered(image_id, cleaned)
    return {"items": cleaned}

@app.get("/images/{image_id}/export.csv")
def export_csv(image_id: str):
    with results_lock:
        data = _load_results(image_id)
        items = data.get("items", [])
        _write_csv_filtered(image_id, items)  # uses current JSON (already cleaned if you pressed Clean)
        p = RESULTS_DIR / f"{image_id}.csv"
        if not p.exists():
            raise HTTPException(404, "no CSV for this image")
    return FileResponse(p, media_type="text/csv", filename=f"{image_id}.csv")

@app.get("/exports/results.zip")
def download_all_csv_zip():
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
        it = items[index]
        if "name" in payload:   it["name"] = payload["name"]
        if "status" in payload: it["status"] = payload["status"]
        items[index] = it
        _save_results(image_id, {"items": items})
        _write_csv_filtered(image_id, items)
    return {"ok": True, "item": it}


@app.post("/images/{image_id}/results/{index}/remove")
def remove_result(image_id: str, index: int):
    with results_lock:
        data = _load_results(image_id)
        items = data.get("items", [])
        if not (0 <= index < len(items)):
            raise HTTPException(404, "result index out of range")
        items[index]["status"] = "removed"
        _save_results(image_id, {"items": items})
        _write_csv_filtered(image_id, items)
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    os.environ.setdefault("DATA_DIR", "./data")
    uvicorn.run("backend.app_local:app", host="127.0.0.1", port=8000, reload=True)

# backend/app_local.py
# Run: uvicorn backend.app_local:app --reload

from __future__ import annotations

# ---------------- PATH SHIM (Windows/PyCharm: allow importing libs/ocr_core) ----------------
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "libs" / "ocr_core"))
# --------------------------------------------------------------------------------------------

import os, io, re, json, zipfile, threading, queue, logging
from uuid import uuid4
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ocr_core.ocr_runner import EasyOCRBackend
from ocr_core.csv_adapter import save_csv, load_csv

# -------------------------- Directories & Globals --------------------------
DATA_DIR = Path(os.getenv("DATA_DIR", "./data")).resolve()
IMAGES_DIR = DATA_DIR / "images"
RESULTS_DIR = DATA_DIR / "results"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# In-memory maps / locks / queues
image_key_by_id: Dict[str, str] = {}
job_q: "queue.Queue[dict]" = queue.Queue()
job_status: Dict[str, str] = {}
results_lock = threading.Lock()

# -------------------------- Storage helper --------------------------
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

# -------------------------- Image index helpers --------------------------
def _parse_image_entry(fname: str):
    """Expect '<image_id>_<originalname.ext>'. Return (image_id, originalname.ext) or (None, None)."""
    if "_" not in fname:
        return None, None
    image_id, original = fname.split("_", 1)
    return image_id, original

def _rebuild_image_index():
    """Scan IMAGES_DIR and reconstruct image_key_by_id (survives restarts)."""
    image_key_by_id.clear()
    for p in IMAGES_DIR.iterdir():
        if not p.is_file():
            continue
        iid, original = _parse_image_entry(p.name)
        if iid and original:
            image_key_by_id[iid] = p.name

# Build the index now (import time)
_held_logging = logging.getLogger("smartkamera")
_rebuild_image_index()

# -------------------------- OCR Backend (GPU toggle) --------------------------
use_gpu = os.getenv("OCR_GPU", "0") == "1"
ocr = EasyOCRBackend(language="de", gpu=use_gpu)

# -------------------------- JSON/CSV helpers --------------------------
def _results_path(image_id: str) -> Path:
    return RESULTS_DIR / f"{image_id}.json"

def _load_results(image_id: str) -> dict:
    p = _results_path(image_id)
    if not p.exists():
        return {"items": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"items": []}

def _save_results(image_id: str, data: dict) -> None:
    _results_path(image_id).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

def _orig_image_filename(image_id: str) -> str:
    """
    Prefer filename recorded in the results JSON (image_filename); else fallback to upload map; else id.jpg.
    """
    rp = _results_path(image_id)
    if rp.exists():
        try:
            data = json.loads(rp.read_text(encoding="utf-8"))
            fn = data.get("image_filename")
            if isinstance(fn, str) and fn.strip():
                return fn
        except Exception:
            pass
    key = image_key_by_id.get(image_id)
    if key and "_" in key:
        return key.split("_", 1)[1]
    return f"{image_id}.jpg"

def _csv_path_for(image_id: str) -> Path:
    img_name = _orig_image_filename(image_id)
    return RESULTS_DIR / Path(img_name).with_suffix(".csv").name

def _ocritems_to_ui_json(items):
    """
    Convert list[OCRItem|dict] to UI schema:
    { "items": [ {"bbox":{x1,y1,x2,y2}, "name":..., "confidence":..., "status":"active"} ] }
    """
    out = []
    for it in items:
        if isinstance(it, dict):
            b = it.get("bbox", {})
            name = it.get("name")
            conf = it.get("confidence")
        else:
            # dataclass-like
            bobj = getattr(it, "bbox", None)
            if isinstance(bobj, dict):
                b = bobj
            else:
                b = {
                    "x1": getattr(bobj, "x1", None),
                    "y1": getattr(bobj, "y1", None),
                    "x2": getattr(bobj, "x2", None),
                    "y2": getattr(bobj, "y2", None),
                }
            name = getattr(it, "name", None)
            conf = getattr(it, "confidence", None)
        out.append({
            "bbox": {
                "x1": int(b["x1"]), "y1": int(b["y1"]),
                "x2": int(b["x2"]), "y2": int(b["y2"]),
            },
            "name": name,
            "confidence": conf,
            "status": "active",
        })
    return {"items": out}

def _write_csv_filtered(image_id: str, items: list[dict]) -> None:
    """
    Write CSV using the original image filename for both:
      - CSV file name
      - 'Bildname' column via save_csv(bildname=...)
    Excludes items with status=='removed'.
    """
    from ocr_core.models import OCRItem, BBox

    img_name = _orig_image_filename(image_id)
    out_csv  = _csv_path_for(image_id)

    active = []
    for it in items:
        if it.get("status") == "removed":
            continue
        b = it["bbox"]
        active.append(
            OCRItem(
                bbox=BBox(
                    x1=int(round(b["x1"])), y1=int(round(b["y1"])),
                    x2=int(round(b["x2"])), y2=int(round(b["y2"]))
                ),
                name=it.get("name"),
                confidence=it.get("confidence"),
                image_id=img_name,  # Bildname comes from the 'bildname' param below
            )
        )
    save_csv(out_csv, active, bildname=img_name)

# -------------------------- Strict Cleaner --------------------------
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
_RE_ONLY_LETTERS_AND_SPACES = re.compile(r"[^A-Za-zÀ-ÖØ-öø-ÿ\s]+")

def _titlecase_if_upper(s: str) -> str:
    return s.title() if s.isupper() else s

def _contains_blacklist(s: str) -> bool:
    return any(w in s for w in BLACKLIST)

def _split_name(name: str) -> List[str]:
    parts = [name]
    for d in SPLIT_DELIMS:
        parts = sum((p.split(d) for p in parts), [])
    return [p.strip() for p in parts if p and p.strip()]

def _strip_specials_and_digits(s: str) -> str:
    s2 = _RE_ONLY_LETTERS_AND_SPACES.sub("", s)
    s2 = re.sub(r"\s+", " ", s2).strip()
    return s2

def _coerce_bbox_int(b: dict) -> dict:
    return {
        "x1": int(round(b["x1"])),
        "y1": int(round(b["y1"])),
        "x2": int(round(b["x2"])),
        "y2": int(round(b["y2"])),
    }

def clean_items(items: List[dict]) -> List[dict]:
    """
    Split -> normalize/titlecase -> spelling -> blacklist -> strip (letters+spaces only)
    -> drop numbers-only & <=2 letters -> dedupe -> reorder by top-left
    """
    active = [it for it in items if it.get("status") != "removed"]
    kept: List[dict] = []
    for it in active:
        raw_name = (it.get("name") or "").strip()
        if not raw_name:
            continue
        parts = _split_name(raw_name) or [raw_name]
        for p in parts:
            p = _titlecase_if_upper(p.strip())
            p = SPELLING.get(p, p)
            if _contains_blacklist(p):
                continue
            p_clean = _strip_specials_and_digits(p)
            # must contain at least one letter; drop if <= 2 letters
            if not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", p_clean):
                continue
            letter_count = len(re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ]", "", p_clean))
            if letter_count <= 2:
                continue
            kept.append({
                "bbox": _coerce_bbox_int(it["bbox"]),
                "name": p_clean,
                "confidence": it.get("confidence"),
                "status": "active",
            })
    # dedupe by (bbox,name) keep higher confidence
    dedup = {}
    for k in kept:
        key = (k["bbox"]["x1"], k["bbox"]["y1"], k["bbox"]["x2"], k["bbox"]["y2"], k["name"])
        if key not in dedup or (k.get("confidence") or 0) > (dedup[key].get("confidence") or 0):
            dedup[key] = k
    kept = list(dedup.values())
    kept.sort(key=lambda it: (it["bbox"]["y1"], it["bbox"]["x1"]))
    return kept

# -------------------------- Worker --------------------------
def worker_loop():
    """
    Background OCR worker:
      - waits for jobs from job_q (job_id, image_id)
      - runs OCR
      - writes JSON in UI schema (+ image_filename)
      - writes CSV named after original image filename
      - updates job_status
    Stop with: job_q.put(None)
    """
    log = logging.getLogger("smartkamera.worker")
    while True:
        job = job_q.get()
        if job is None:
            job_q.task_done()
            break
        job_id = job.get("job_id")
        image_id = job.get("image_id")
        try:
            job_status[job_id] = "running"

            # Resolve image path
            key = image_key_by_id.get(image_id)
            if not key:
                raise RuntimeError(f"image_id not found: {image_id}")
            image_path = storage.get_path(key)

            # OCR -> list[OCRItem]
            items = ocr.run(str(image_path))

            # Build JSON
            img_name = _orig_image_filename(image_id)
            json_out = _ocritems_to_ui_json(items)
            json_out["image_filename"] = img_name

            with results_lock:
                # JSON
                _results_path(image_id).write_text(
                    json.dumps(json_out, ensure_ascii=False),
                    encoding="utf-8"
                )
                # CSV named after original filename; Bildname=original
                csv_path = _csv_path_for(image_id)
                save_csv(csv_path, items, bildname=img_name)

            job_status[job_id] = "done"
            try:
                log.info(f"OCR finished: image_id={image_id} items={len(json_out['items'])} csv={csv_path.name}")
            except Exception:
                pass
        except Exception as e:
            job_status[job_id] = "error"
            try:
                log.exception(f"OCR job failed: job_id={job_id} image_id={image_id}: {e}")
            except Exception:
                pass
        finally:
            job_q.task_done()

# Start worker thread
threading.Thread(target=worker_loop, daemon=True).start()

# -------------------------- FastAPI + Static UI --------------------------
app = FastAPI(title="Smart_Kamera_Web (local)", version="0.3.0")
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/ui", StaticFiles(directory=STATIC_DIR, html=True), name="ui")

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/ui")

# -------------------------- Schemas --------------------------
class UploadResp(BaseModel):
    image_id: str
    filename: str

class JobResp(BaseModel):
    job_id: str

class BatchReq(BaseModel):
    image_ids: Optional[List[str]] = None

class BatchResp(BaseModel):
    job_ids: List[str]

# -------------------------- Endpoints --------------------------
@app.get("/health")
def health():
    return {"status": "ok", "gpu": use_gpu}

@app.on_event("startup")
def on_startup():
    _rebuild_image_index()

@app.get("/images")
def list_images():
    # Always scan disk so it survives restarts
    items = []
    for p in sorted(IMAGES_DIR.iterdir()):
        if not p.is_file():
            continue
        iid, original = _parse_image_entry(p.name)
        if not iid:
            continue
        items.append({"image_id": iid, "filename": original})
    # refresh in-memory map
    for it in items:
        image_key_by_id[it["image_id"]] = f'{it["image_id"]}_{it["filename"]}'
    return {"items": items}

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

@app.get("/images/{image_id}/file")
def get_image_file(image_id: str):
    # Try map
    key = image_key_by_id.get(image_id)
    if key:
        p = storage.get_path(key)
        if p.exists():
            return FileResponse(p)
    # Fallback scan
    for q in IMAGES_DIR.iterdir():
        if not q.is_file():
            continue
        iid, _ = _parse_image_entry(q.name)
        if iid == image_id:
            image_key_by_id[image_id] = q.name
            return FileResponse(q)
    raise HTTPException(404, "file not found on disk")

@app.delete("/images/{image_id}")
def delete_image(image_id: str, delete_results: bool = True):
    # delete image file
    removed = False
    key = image_key_by_id.pop(image_id, None)
    if key:
        p = storage.get_path(key)
        if p.exists():
            p.unlink(missing_ok=True)
            removed = True
    if not removed:
        for q in IMAGES_DIR.iterdir():
            if not q.is_file():
                continue
            iid, _ = _parse_image_entry(q.name)
            if iid == image_id:
                q.unlink(missing_ok=True)
                removed = True
                break
    # delete results if requested
    if delete_results:
        (_results_path(image_id)).unlink(missing_ok=True)
        _csv_path_for(image_id).unlink(missing_ok=True)
    if not removed:
        raise HTTPException(404, "image not found")
    return {"ok": True}

@app.delete("/images")
def delete_all_images(delete_results: bool = False):
    count = 0
    for q in IMAGES_DIR.iterdir():
        if q.is_file():
            q.unlink(missing_ok=True)
            count += 1
    image_key_by_id.clear()
    if delete_results:
        for r in RESULTS_DIR.glob("*.json"):
            r.unlink(missing_ok=True)
        for r in RESULTS_DIR.glob("*.csv"):
            r.unlink(missing_ok=True)
    return {"deleted": count}

@app.post("/ocr/jobs", response_model=JobResp)
def create_ocr_job(image_id: str):
    # ensure image exists
    if image_id not in image_key_by_id:
        # fallback scan
        found = False
        for q in IMAGES_DIR.iterdir():
            iid, _ = _parse_image_entry(q.name)
            if iid == image_id:
                image_key_by_id[image_id] = q.name
                found = True
                break
        if not found:
            raise HTTPException(404, "image_id not found")
    job_id = str(uuid4())
    job_status[job_id] = "queued"
    job_q.put({"job_id": job_id, "image_id": image_id})
    return JobResp(job_id=job_id)

@app.post("/ocr/jobs/batch", response_model=BatchResp)
def create_ocr_jobs_batch(req: BatchReq):
    ids = req.image_ids or [iid for iid, _ in ( _parse_image_entry(p.name) for p in IMAGES_DIR.iterdir() ) if iid]
    job_ids: list[str] = []
    for image_id in ids:
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
    """
    Return JSON; if missing/empty, rebuild from CSV named after original image file,
    persist JSON, then return it (auto-heal).
    """
    p = _results_path(image_id)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("items"), list) and data["items"]:
                return data
        except Exception:
            pass

    # Rebuild from CSV
    csv_path = _csv_path_for(image_id)
    if not csv_path.exists():
        raise HTTPException(404, "no results for this image")
    try:
        ocr_items = load_csv(csv_path)
    except Exception as e:
        raise HTTPException(500, f"failed to load CSV: {e}")

    data = _ocritems_to_ui_json(ocr_items)
    # image_filename from CSV (OCRItem.image_id carries Bildname we wrote)
    try:
        first = next(iter(ocr_items))
        image_filename = getattr(first, "image_id", None) or _orig_image_filename(image_id)
        if image_filename:
            data["image_filename"] = image_filename
    except StopIteration:
        data["image_filename"] = _orig_image_filename(image_id)

    with results_lock:
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data

@app.post("/images/{image_id}/clean")
def clean_results(image_id: str):
    """Clean current results: rewrite JSON to cleaned active items and refresh CSV."""
    with results_lock:
        data = _load_results(image_id)
        items = data.get("items", [])
        cleaned = clean_items(items)
        img_name = _orig_image_filename(image_id)
        new_payload = {"image_filename": img_name, "items": cleaned}
        _save_results(image_id, new_payload)
        _write_csv_filtered(image_id, cleaned)
    return {"items": cleaned}

@app.get("/images/{image_id}/export.csv")
def export_csv(image_id: str):
    with results_lock:
        data = _load_results(image_id)
        items = data.get("items", [])
        _write_csv_filtered(image_id, items)  # ensure latest & correct path/filename
        p = _csv_path_for(image_id)
        if not p.exists():
            raise HTTPException(404, "no CSV for this image")
    return FileResponse(p, media_type="text/csv", filename=p.name)

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
        _save_results(image_id, {"image_filename": _orig_image_filename(image_id), "items": items})
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
        _save_results(image_id, {"image_filename": _orig_image_filename(image_id), "items": items})
        _write_csv_filtered(image_id, items)
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    os.environ.setdefault("DATA_DIR", "./data")
    uvicorn.run("backend.app_local:app", host="127.0.0.1", port=8000, reload=True)

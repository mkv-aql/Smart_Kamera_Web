from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from uuid import uuid4
from pathlib import Path
import os
import redis
import json

from ocr_core.json_adapter import to_json
from ocr_core.ocr_runner import EasyOCRBackend
from .storage_local import LocalStorage
from .models import OCRJobStatus

# simple “jobs” store in Redis for now
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

DATA_DIR = Path(os.getenv("DATA_DIR", "./data")).resolve()
IMAGES_DIR = DATA_DIR / "images"
RESULTS_DIR = DATA_DIR / "results"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Smart_Kamera_Web API", version="0.1.0")
storage = LocalStorage(IMAGES_DIR)

class UploadResp(BaseModel):
    image_id: str
    filename: str

class JobResp(BaseModel):
    job_id: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/images", response_model=UploadResp)
async def upload_image(file: UploadFile = File(...)):
    image_id = str(uuid4())
    key = f"{image_id}_{file.filename}"
    data = await file.read()
    storage.put(key, data)
    # remember mapping
    r.hset("images", image_id, key)
    return UploadResp(image_id=image_id, filename=file.filename)

@app.post("/ocr/jobs", response_model=JobResp)
def create_ocr_job(image_id: str):
    key = r.hget("images", image_id)
    if not key:
        raise HTTPException(404, "image_id not found")
    job_id = str(uuid4())
    # enqueue by writing a list item the worker will poll
    r.lpush("ocr_queue", json.dumps({"job_id": job_id, "image_key": key}))
    r.hset("job_status", job_id, OCRJobStatus.queued)
    return JobResp(job_id=job_id)

@app.get("/ocr/jobs/{job_id}")
def job_status(job_id: str):
    status = r.hget("job_status", job_id) or OCRJobStatus.unknown
    return {"job_id": job_id, "status": status}

@app.get("/images/{image_id}/results")
def get_results(image_id: str):
    result_path = RESULTS_DIR / f"{image_id}.json"
    if not result_path.exists():
        raise HTTPException(404, "no results for this image")
    return json.loads(result_path.read_text())

@app.get("/images/{image_id}/export.csv")
def export_csv(image_id: str):
    csv_path = RESULTS_DIR / f"{image_id}.csv"
    if not csv_path.exists():
        raise HTTPException(404, "no CSV for this image")
    return FileResponse(csv_path, media_type="text/csv", filename=f"{image_id}.csv")

import os, json, time
from pathlib import Path
import redis
from ocr_core.ocr_runner import EasyOCRBackend
from ocr_core.json_adapter import to_json
from ocr_core.csv_adapter import save_csv

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATA_DIR = Path(os.getenv("DATA_DIR", "./data")).resolve()
IMAGES_DIR = DATA_DIR / "images"
RESULTS_DIR = DATA_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
ocr = EasyOCRBackend(language="de", gpu=False)

def main():
    print("Worker started. Waiting for jobs…")
    while True:
        raw = r.brpop("ocr_queue", timeout=5)  # blocks up to 5s, returns (key, value) or None
        if raw is None:
            continue
        _, payload = raw
        job = json.loads(payload)
        job_id = job["job_id"]
        image_key = job["image_key"]

        try:
            r.hset("job_status", job_id, "running")
            image_path = IMAGES_DIR / image_key
            items = ocr.run(str(image_path))

            # store as JSON
            json_out = to_json(items)
            # image_id is prefix before '_' (from backend key format)
            image_id = image_key.split("_", 1)[0]
            (RESULTS_DIR / f"{image_id}.json").write_text(json.dumps({"items": json_out}, ensure_ascii=False))

            # also export CSV (frontend parity)
            save_csv(RESULTS_DIR / f"{image_id}.csv", items, bildname=image_id)

            r.hset("job_status", job_id, "done")
            print(f"Job {job_id}: done ({len(items)} items)")
        except Exception as e:
            r.hset("job_status", job_id, "error")
            print(f"Job {job_id}: ERROR {e}")

if __name__ == "__main__":
    main()

# backend/run_local.py
import os
import sys
import pathlib
import uvicorn

# Ensure project root is on sys.path so "backend.app_local" can be imported
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Put data under backend/data by default
os.environ.setdefault("DATA_DIR", str(ROOT / "backend" / "data"))

if __name__ == "__main__":
    # IMPORTANT: run from project root or this file; the sys.path shim above handles both
    uvicorn.run("backend.app_local:app", host="127.0.0.1", port=8000, reload=True)

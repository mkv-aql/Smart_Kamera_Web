import os
import uvicorn

if __name__ == "__main__":
    # keep data under project folder
    os.environ.setdefault("DATA_DIR", "./data")
    # start FastAPI app (the in-process worker version)
    uvicorn.run(
        "backend.app_local:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )

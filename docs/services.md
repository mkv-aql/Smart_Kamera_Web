plan:

api – FastAPI web server (auth, uploads, CRUD, export).

worker – background OCR runner (Celery/RQ), writes results to DB/storage.

db – PostgreSQL database.

cache – Redis (queue broker + result backend).

storage – S3-compatible object storage (MinIO) for images/thumbnails.

frontend – React app (served by Vite in dev; via proxy in prod).

proxy – Nginx/Caddy reverse proxy & TLS (often only in prod).
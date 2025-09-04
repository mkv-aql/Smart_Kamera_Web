# ADR-0001: Web architecture for OCR app
Date: 2025-09-02
Status: Proposed (to be Adopted)

Context:
- Desktop PyQt app hard to distribute; move to web.
- Needs async OCR, image storage, CSV-equivalent editing, auth, audit.

Decision:
- Backend: FastAPI
- Frontend: React (Vite)
- DB: PostgreSQL
- Storage: MinIO (S3-compatible)
- Jobs: Celery + Redis
- API: REST, with SSE for job progress (future)
- Deploy: Docker Compose (dev), containers + HTTPS (prod)

Consequences:
- Clear separation of concerns; horizontally scalable workers.
- Slight complexity (Redis, Celery, MinIO), but operationally standard.
- CSV moves to DB rows + export endpoint.

Layout:
- Smart_Kamera_Web/
  - backend/        # FastAPI app
  - worker/         # Celery worker (imports backend OCR code)
  - frontend/       # React app
  - infra/          # docker-compose, Nginx/Caddy, env templates
  - docs/




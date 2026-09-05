# Deploying Invoxa

Invoxa is a two-service architecture: a Python FastAPI backend and a React/Vite
frontend, sharing Supabase as the data plane. This document summarises the
hosting targets.

## Backend - Render (free tier)

1. Connect the GitHub repository in [Render](https://render.com).
2. The repository ships a [render.yaml](../render.yaml) Blueprint that creates a
   single Docker web service named `invoxa-api`.
3. Supply the four required secrets (`SUPABASE_URL`,
   `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SERVICE_KEY`, `GEMINI_API_KEY`) in the
   service's environment tab.  The Blueprint declares them as `sync: false` so
   they remain platform-managed.
4. Render will:
   - build using `backend/Dockerfile` (python:3.12-slim + tesseract-ocr);
   - run `uvicorn app.main:app --host 0.0.0.0 --port $PORT`;
   - ping `/health`.  A 200 response flips the service from "sleeping" to
     "awake" when traffic returns.
5. Free-tier cold starts are 60-90s.  Frontend uses `HealthGate` to show a
   warm-up spinner during the wake-up.

## Frontend - Vercel (Hobby)

1. Import the repository and set the **Root Directory** to `frontend`.
2. The framework preset "Vite" should auto-detect; if not, set build command
   `npm run build` and output directory `dist`.
3. Add the env vars from [`frontend/.env.example`](../frontend/.env.example):
   - `VITE_API_BASE_URL` -> `https://<your-render-subdomain>.onrender.com`
   - `VITE_SUPABASE_URL`
   - `VITE_SUPABASE_PUBLISHABLE_KEY`
4. Vercel serves the static bundle from its global CDN.  No additional
   configuration needed.
5. Because the project is non-commercial, Vercel Hobby is acceptable per the
   audit log guidance.

## Database - Supabase
|
|4|1. Apply migrations manually or via the Supabase CLI:
   ```bash
   psql "$DATABASE_URL" -f migrations/0001_init.sql
   psql "$DATABASE_URL" -f scripts/seed.sql   # optional sample vendors
   ```
2. Create the **`invoices`** Storage bucket (1GB free tier) with
   `raw/` and `processed/` paths exposed as public-read if you want the
   frontend to download previews.
3. Note the publishable (anon) key and service-role key for the backend.

## Local Docker Compose

```bash
docker-compose up --build
```

This boots a Postgres 16 container alongside the backend for a no-Supabase
local loop.

## Pre-commit Hooks

Install the pre-commit framework and hooks:
```bash
pip install pre-commit
pre-commit install
```
This installs the gitleaks secret scanner, which runs on every commit and
in CI via the `secret-scan` job in `.github/workflows/ci.yml`.

## Troubleshooting

### Backend won't start - missing env vars
- Ensure all `SUPABASE_*` and `GEMINI_API_KEY` variables are set. The service
  raises `RuntimeError` at import time if `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`,|
  or `SUPABASE_SERVICE_KEY` are missing.

### Frontend build fails - `npm ci` errors
- Use `npm install` instead of `npm ci` (no lock file is committed yet).

### Cold starts on Render
- Free-tier services sleep after 15 minutes of inactivity and take 60-90s to
  wake. The frontend's `HealthGate` component shows a warm-up spinner during this
  window. Consider a cron-job.org keep-alive for always-on behaviour.

### Tesseract not found (Docker build)
- The `backend/Dockerfile` installs `tesseract-ocr` with `eng` and `hin` language
  packs. If building locally, ensure the apt packages are installed.

### Tests fail locally - missing `supabase` package
- The `supabase` Python package may not be installed in your local environment.|
  This is expected for running the test suite only (the code uses lazy imports|
  so tests pass with placeholder env vars and a faked client).
  Run `pip install -r backend/requirements-dev.txt` to install all test deps.

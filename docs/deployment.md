# Deploying Invoxa

Invoxa is a two-service architecture: a Python FastAPI backend and a React/Vite
frontend, sharing Supabase as the data plane. Both services deploy to **Vercel**
from one repository and share one domain.

## Hosting - Vercel (both services)

[`vercel.json`](../vercel.json) at the repo root owns the whole deployment:

- **frontend** — Vite project rooted at `frontend/`, with an SPA rewrite
  (`/(.*) -> /index.html`) so client-side routes like `/app/invoices/<id>`
  work on hard refresh.
- **backend** — FastAPI as a Python serverless function rooted at `backend/`,
  entrypoint [`api/index.py`](../backend/api/index.py), with the function
  timeout raised to 60s so long OCR/AI extractions fit.

Public routing is handled by the project-level rewrites:

| Path | Served by |
| --- | --- |
| `/api/*` | backend function |
| `/health` | backend function |
| everything else | frontend (SPA) |

### Steps

1. Import the GitHub repository into Vercel. The `vercel.json` services are
   picked up automatically — no per-project root-directory tweaks needed.
2. Configure the secrets as project environment variables (nothing sensitive
   is committed):
   - `SUPABASE_URL`
   - `SUPABASE_PUBLISHABLE_KEY`
   - `SUPABASE_SERVICE_KEY`
   - `SECRET_KEY` — random 64-hex string; required for stable JWT sessions
   - `GEMINI_API_KEY` — optional, enables the AI vision/categorization assists
3. Deploy. Both halves go live together on the same domain.
4. Verify `https://<your-deployment>.vercel.app/health` returns
   `{"status": "ok"}`.

### Cold starts

Vercel serverless functions may idle between requests; the first request after
an idle period pays a short cold-start (typically a few seconds, not minutes).
The frontend's `HealthGate` component pings `/health` and shows a warm-up
spinner so the app never cascades into errors during that window.

> Note: `render.yaml` and `backend/Dockerfile` in the repository are legacy
> artifacts from an earlier hosting experiment and are not used by the Vercel
> deployment.

## Database - Supabase

1. Apply migrations manually or via the Supabase CLI, in order:

   ```bash
   psql "$DATABASE_URL" -f migrations/0001_init.sql
   psql "$DATABASE_URL" -f migrations/0006_line_items.sql
   ```

   (`0002_auth.sql`–`0005_tax.sql` are kept out of the repo by `.gitignore`;
   apply them with `python scripts/apply_0004.py`, `python scripts/apply_0005.py`
   — and `python scripts/apply_0006.py` — or by hand in the Supabase SQL editor.)

2. Create the **invoices** Storage bucket with `raw/` and `processed/` paths
   exposed as public-read if you want the frontend to download previews.
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
- Ensure all `SUPABASE_*`, `SECRET_KEY`, and (optionally) `GEMINI_API_KEY`
  variables are set. The service raises `RuntimeError` at import time if
  `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, or `SUPABASE_SERVICE_KEY`
  are missing.

### Frontend build fails - `npm ci` errors
- Use `npm install` instead of `npm ci` (no lock file is committed yet).

### Function timeout on long extractions
- The backend function runs with `maxDuration: 60` (seconds). Scanned PDFs
  that need the OCR + AI fallback path stay well inside this; if you add
  heavier processing, raise the value in `vercel.json`.

### Tesseract not found (Docker build)
- The legacy `backend/Dockerfile` installs `tesseract-ocr` with `eng` and
  `hin` language packs. This only matters for the optional local Docker
  setup; the Vercel deployment does not use Docker.

### Tests fail locally - missing `supabase` package
- The `supabase` Python package may not be installed in your local
  environment. This is expected for running the test suite only (the code
  uses lazy imports so tests pass with placeholder env vars and a faked
  client). Run `pip install -r backend/requirements-dev.txt` to install all
  test deps.

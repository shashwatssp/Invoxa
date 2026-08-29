# Invoxa — Progress & Development Plan

> For internal tracking and review by domain experts. Last updated: Aug 29, 2026.

---

## 1. Project Overview

**Invoxa** is an AI-powered invoice automation tool for Indian micro-SMEs.
It processes invoices through an OCR-first, rules-based pipeline, with a
Gemini vision API fallback for low-confidence extractions.

### Tech Stack

| Layer         | Tech                                              |
|---------------|--------------------------------------------------|
| Backend       | Python 3.12 + FastAPI on Render (free tier)       |
| Frontend      | React 18 + Vite 5 + TypeScript + Shadcn UI        |
| Data Layer    | Supabase Postgres + Storage                       |
| OCR           | Tesseract 5 (--oem 1, --psm 6) + PyMuPDF + pdfplumber |
| Validation    | python-stdnum (GSTIN mod-36) + bharatutils        |
| Fallback LLM  | Gemini 2.5 Flash (~250 req/day free)              |
| Secret Scanning | gitleaks (pre-commit + CI)                       |

### Live Architecture Diagram

```
User Browser → Vercel Frontend → Render Python Backend → (OCR + regex OR Gemini API) → Supabase
```

---

## 2. Current Build Status (Aug 29, 2026)

### Sprint Completion

| Sprint | Date       | Status      | Commit   | Key Deliverables |
|--------|------------|-------------|----------|-----------------|
| #1     | Aug 26     | ✅ Done     | 769bfe0  | Monorepo scaffold, gitignore, env template, license |
| #2     | Aug 27     | ✅ Done     | 3ac73ce  | Postgres schema (6 tables), migrations, db connection |
| #3     | Aug 28     | ✅ Done     | 3e9de10  | OCR-first extraction pipeline (PyMuPDF, Tesseract, pdfplumber, regex rules, 5-strategy GSTIN finder, arithmetic validation, Gemini fallback) |
| #5     | Aug 29     | ✅ Done     | cb664ac  | Validation layer (GSTIN checksum, anomaly detection, duplicate detection) |
| #6     | Aug 30     | ✅ Done (local) | 1bd76fa | FastAPI API endpoints |
| #7     | Aug 31     | ✅ Done (local) | 0dbfe2f | Frontend React components |
| #8     | Sep 1      | ✅ Done (local) | 8dee70f | Docker-compose, environment setup |
| #9     | Sep 2     | ✅ Done (local) | 90027ae | Review queue + correction logging |
| #10    | Sep 3     | ✅ Done (local) | eebfef9 | CSV export for Tally/Zoho |
| #11    | Sep 4     | ✅ Done (local) | b5e6f74 | Weekly digest generation |
| #12    | Sep 5     | ✅ Done (local) | 3638d97 | Secret scanning + CI |
| #13    | Sep 6     | ✅ Done (local) | 47a0996 | Docs polish + troubleshooting |
| #14    | Sep 7     | ✅ Done (local) | 726cf11 | Close-out commits |

### Remote vs Local Status

- **Remote** (`origin/main`): Pushed through Aug 29 — Sprints #1, #2, #3, #5 (`cb664ac`)
- **Local** (`master`): All 14 sprints committed + iterative improvements (Sep 4–7 commits are local-only per developer preference)

### Test Suite

```
117 passed, 1 skipped (backend only)
```

Test breakdown by file:
- `test_corrections.py`: 9 tests (correction logging, invoice-level patching, pending review)
- `test_digest.py`: 15 tests (date parsing, amount coercion, vendor ranking, due-soon, digest generation)
- `test_export_csv.py`: 10 tests (CSV format, date/amount mapping, headers, status filter)
- `test_anomaly.py`: 6 tests (anomaly detection, flag-for-review logic)
- Other tests: ~77 tests across extraction, validation, models, API endpoints

---

## 3. What Has Been Built — Detailed Breakdown

### 3.1 Backend: Extraction Pipeline (`app/extraction/`)

**Files:**
- `pipeline.py` — Main extraction orchestrator
- `ocr.py` — Text extraction (PyMuPDF first, Tesseract OCR fallback)
- `regex_rules.py` — Regex-based field extraction
- `gemini_fallback.py` — Gemini 2.5 Flash vision API fallback

**Pipeline steps:**
1. PDF text-layer extraction via PyMuPDF (fitz) for speed
2. If no text layer, PyMuPDF renders pages to images at 300 DPI, Tesseract OCR with `--oem 1 --psm 6`
3. pdfplumber for layout-preserving table extraction from digital PDFs
4. Regex rules extract: vendor name, vendor GSTIN, invoice number, invoice date, due date, amount, tax amount, total amount, line items
5. GSTIN validation via python-stdnum (official mod-36 Luhn checksum + direct mod-36)
6. **5-strategy GSTIN candidate finder**: structured regex, fuzzy OCR, positional context, checksum-only, numeric scan
7. Arithmetic total validation (sum of line items + tax == Grand Total)
8. Confidence scoring per field (regex match + OCR word confidence + checksum validation)
9. If overall confidence < 0.7, fall back to Gemini 2.5 Flash vision API
10. Results stored in Supabase

**Regex Patterns:**
- GSTIN: `\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]`
- Invoice number: `(?:Invoice\s*(?:No|Number|#)\.?\s*[:−]?\s*)([\w\/\-]+)`
- Date: `(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4})`
- Amount: `(?:Grand\s*Total|Total|Amount)[^₹\d]{0,25}(?:Rs\.?|INR|₹)?\s*([\d,]+\.\d{0,2})`
- Taxes: `\b(CGST|SGST|IGST|UTGST)\b[^\₹\d\n]{0,30}(?:Rs\.?|INR|₹)?\s*([\d,]+\.\d{2})`

### 3.2 Backend: Validation Layer (`app/validation/`)

**Files:**
- `gstin.py` — GSTIN mod-36 checksum + python-stdnum cross-check
- `anomaly.py` — `detect_anomalies` (6 anomaly types) and `should_flag_for_review`
- `duplicate.py` — `find_duplicates`, `is_duplicate`, `_amounts_similar`, `_amount_similarity`
- `__init__.py` — Re-exports all validation functions

**Anomaly checks:**
1. Missing critical fields (invoice_number, amount, vendor_gstin)
2. Amount mismatch (line items + tax != total)
3. Future invoice date
4. Due date before invoice date
5. Negative or zero amount
6. Very low overall confidence (< 0.3)

### 3.3 Backend: API Endpoints (`app/api/`)

**Routes** (all under `/api` prefix, mounted in `app/main.py` with lifespan):

| Route                           | Method | Function                          |
|---------------------------------|--------|-----------------------------------|
| `/health`                       | GET    | Warm-up endpoint                  |
| `/invoices`                     | GET    | List all invoices with status     |
| `/invoices`                     | POST   | Register invoice after upload     |
| `/invoices/{id}`               | GET    | Single invoice + extraction fields|
| `/invoices/{id}/extract`       | POST   | Trigger OCR extraction          |
| `/invoices/{id}/correct`       | POST   | Save human correction             |
| `/review/queue`                | GET    | List flagged invoices             |
| `/review/{id}/resolve`         | POST   | Mark as reviewed/auto-approved    |
| `/export/csv`                  | GET    | Generate Tally/Zoho CSV           |
| `/digest`                      | GET    | Weekly plain-English summary      |

**Key files:**
- `main.py` — FastAPI app bootstrap, health endpoint, lifespan
- `invoices.py` — UploadFile multipart handling, extraction orchestration
- `review.py` — Review queue + correction API
- `export.py` — CSV export (delegates to `app/export/csv_export.py`)
- `digest.py` — Digest API (delegates to `app/digest/generator.py`)

### 3.4 Backend: Database Layer (`app/database.py`)

Supabase Data Access Layer with these functions:
- `get_invoices()`, `get_invoice(invoice_id)`
- `create_invoice(storage_path, vendor_id)`
- `update_invoice_status(invoice_id, status)`
- `save_extraction_result(invoice_id, result)`
- `save_correction(invoice_id, correction)`
- `get_or_create_vendor(gstin, name)`
- `add_to_review_queue(invoice_id, reason)`
- `get_review_queue()`, `resolve_review_item(review_id, approved)`

`app/supabase.py` uses lazy imports for the `supabase` package (so tests pass without it installed locally), with a module-level singleton client.

### 3.5 Backend: Correction Logging (`app/review/corrections.py`)

Three main functions:

1. **`log_correction(review_id, field_name, new_value)`** → `Correction`
   - Validates inputs (raises `ValueError` for empty fields)
   - Fetches review row (raises `LookupError` if not found)
   - Records old value from `extraction_fields` table
   - Inserts audit row into `corrections` table
   - Returns populated `Correction` model

2. **`apply_correction_to_invoice(correction)`** → `dict`
   - Updates matching `extraction_fields` row with new value + confidence=1.0
   - If field is invoice-level (`INVOICE_LEVEL_FIELDS`), patches `invoices` table
   - Inserts new `extraction_fields` row if none exists

3. **`has_pending_review(review_id)`** → `bool`
   - Checks if a review queue item exists and is still "pending"

`INVOICE_LEVEL_FIELDS = {"invoice_number", "amount", "due_date"}` — fields that live directly on the `invoices` table.

### 3.6 Backend: CSV Export (`app/export/csv_export.py`)

- `CSV_HEADERS = [date, voucher_type, voucher_number, name, gstin, tax_amount, amount, total_amount, narration, status]`
- Date formatting: `YYYY-MM-DD` → `DD/MM/YYYY` (Tally/Zoho convention)
- Amount formatting: two decimals
- Status filtering support via `?status=` query param
- `csv.DictWriter` with `lineterminator="\n"` (cross-platform safe)
- Two entry points: `build_csv(status)` and `preview_csv_rows(status)`

### 3.7 Backend: Weekly Digest (`app/digest/generator.py`)

- `Digest` dataclass with `to_dict()` (uses `dataclasses.asdict`)
- `generate_digest(window_days=7)` — aggregates invoices in rolling window:
  - Counts by status (auto_approved, flagged, exported)
  - Total amount
  - Top vendors by spend (default top 5)
  - Due-soon invoices (within 5 days)
  - Plain-English summary lines
- Helper functions: `_parse_date` (ISO + Indian DD/MM/YYYY), `_coerce_amount`, `_top_vendors`, `_due_soon`, `_build_summary_lines`

### 3.8 Backend: Data Models (`app/models/invoice.py`)

- `InvoiceStatus` enum: `pending`, `flagged`, `auto_approved`, `reviewed`, `exported`
- `Invoice`, `Vendor`, `ExtractionField`, `ExtractionResult`, `Correction` Pydantic models

### 3.9 Frontend: React Components (`frontend/src/`)

**Routes** (behind `HealthGate`):
- `/` — `Dashboard` (stats, CSV download, weekly digest)
- `/upload` — `Upload` (drag-drop + Supabase Storage upload + `/api/invoices/upload`)
- `/review` — `ReviewQueue` (lists flagged invoices, supports corrections/approve)

**Key files:**
- `App.tsx` — Router + nav + HealthGate wrapper
- `HealthGate.tsx` — Polls `/health` on mount, shows spinner during backend warm-up, error state with retry
- `lib/api.ts` — axios client with configurable `VITE_API_BASE_URL`, typed API functions
- `lib/format.ts` — Display formatting helpers
- `index.css` — Hand-rolled CSS variables (no Tailwind dependency installed)
- `vite.config.ts` — Vite 5 + React plugin, `@` alias, dev server with proxy config

### 3.10 Infrastructure

- `render.yaml` — Render Blueprint (backend free tier, health check `/health`)
- `backend/Dockerfile` — `python:3.12-slim` + tesseract-ocr (eng, hin)
- `migrations/0001_init.sql` — 6-table schema (vendors, invoices, extraction_fields, review_queue, corrections, + 1)
- `scripts/seed.sql` — Sample vendor data
- `.gitleaks.toml` — Secret scanning config with allowlist (.env.example, README.md, docs/)
- `.pre-commit-config.yaml` — gitleaks pre-commit hook
- `.github/workflows/ci.yml` — CI: backend syntax check + ruff lint, frontend type-check + build, secret-scan (gitleaks)

---

## 4. Environment & Limitations

### Local Environment
- **OS**: Windows (PowerShell 5.1)
- **Python**: 3.13.7 at `C:\Python313`
- **Node/npm**: Not available in current environment; frontend validation limited
- **Supabase**: Not installed locally — `app/supabase.py` uses lazy imports; `conftest.py`-style test monkeypatching provides placeholder env vars via test fixtures

### Dependencies
Backend `requirements.txt` includes: fastapi, uvicorn, supabase, pytesseract, pdfplumber, PyMuPDF, pillow, python-stdnum, bharatutils, httpx, python-dotenv, python-multipart, pydantic
Dev: pytest, pytest-cov, ruff

### Known Issues / Limitations
1. No `package-lock.json` — `npm ci` fails in CI (fixed to `npm install`)
2. `ruff check` has `|| true` in CI (doesn't fail build yet)
3. `datetime.utcnow()` deprecation warnings fixed in Sprint #11 work
4. Frontend `npm run lint` not configured (no ESLint config)
5. `INVOICE_LEVEL_FIELDS` constant defined but was previously unused in correction application logic (now utilized)

---

## 5. Proposed Roadmap (Post-Aug 29)

### Sprint #14 (Aug 29 — remaining local work)

**Completed locally:**
- ✅ Sprint #11: Weekly digest generation + tests (15 tests)
- ✅ Sprint #12: Secret scanning + CI fixes
- ✅ Sprint #13: Docs polish
- ✅ Iterative improvements: datetime fix, HealthGate fix, invoice-level correction patching

### Sprint #15: Testing Hardening

1. **Add `conftest.py`** to `backend/tests/` — set placeholder env vars so tests don't depend on monkeypatched fixtures
2. **Add fixture-based DB mocking** pattern for all test files (standardize the FakeClient approach)
3. **Add extraction pipeline tests** — test OCR text → regex extraction → confidence scoring → anomaly detection flow
4. **Add API endpoint tests** — test each FastAPI route with `TestClient`
5. **Add frontend type-check validation** — ensure `tsc --noEmit` passes (currently can't verify locally)

### Sprint #16: Error Handling & Production Readiness

1. **Structured error responses** — all FastAPI endpoints should return proper HTTP status codes + error messages
2. **`app/main.py` lifespan** — proper Supabase client initialization + cleanup
3. **Logging** — add structured logging (not `print`) with levels; use `structlog` or stdlib `logging`
4. **Retry logic** — Supabase client should have retry for transient failures
5. **Health endpoint** — include more diagnostics (DB connectivity, Supabase status)

### Sprint #17: Security & Hardening

1. **Verify `gitleaks.toml` allowlist** — ensure no real secrets slip through
2. **Add rate limiting** to FastAPI (e.g., `slowapi` or middleware)
3. **Validate file types** on `/invoices/upload` — reject non-PDF/non-image uploads
4. **Input sanitization** — validate all API inputs with Pydantic
5. **Add security headers** — `X-Content-Type-Options`, `X-Frame-Options`, etc.

### Sprint #18: Frontend Polish

1. **Add ESLint** config + linting script (currently `npm run lint` would fail)
2. **Fix `tsconfig.json`** — ensure strict mode + path aliases work
3. **Add error boundaries** in React components
4. **Add loading states** for all API calls (not just HealthGate)
5. **Add unit tests for frontend** (Vitest + React Testing Library)

### Sprint #19: Documentation & Deployment

1. **Complete `ARCHITECTURE.md`** — add deployment architecture diagram
2. **Add troubleshooting section** — already done in Sprint #13 docs
3. **Add `Makefile`** at repo root for common dev commands (`make test`, `make lint`, `make dev`)
4. **Docker compose validation** — test local docker-compose setup builds
5. **CI improvement** — remove `|| true` from ruff, install from `requirements-dev.txt`

### Sprint #20: Future Stretch Goals

1. **Multi-language OCR** — support for Tamil, Telugu, Kannada (Indian language invoices)
2. **Vendor categorization** — auto-categorize vendors by industry (already has `app/categorization/` stub)
3. **Export formats** — Excel (XLSX) + JSON export in addition to CSV
4. **Email digest** — automated weekly email to accountant with digest summary
5. **Batch processing** — process multiple invoices at once
6. **Dark mode** — frontend theme toggle

---

## 6. Git History (Recent)

```
726cf11 chore: Sprint #14 close-out - all wiring verified, 115 tests passing
47a0996 chore: docs polish - troubleshooting, pre-commit hooks, README updates
3638d97 chore: fix CI secret-scan job, add gitleaks pre-commit hook
b5e6f74 feat: weekly digest generation with vendor ranking, due-soon alerts, and summary
eebfef9 feat: CSV export for Tally/Zoho with row mapping and date formatting
90027ae feat: review queue correction logging + lazy supabase client
8dee70f chore: docker-compose, environment setup
0dbfe2f feat: frontend React components (Upload, ReviewQueue, Dashboard)
1bd76fa feat: FastAPI API endpoints (invoices, review, export, digest)
cb664ac feat: validation layer with anomaly detection, duplicate detection, and enhanced GSTIN checksum
3e9de10 feat: OCR-first extraction pipeline
3ac73ce feat: postgres schema and migrations + db connection
769bfe0 chore: scaffold monorepo, gitignore, env template, license
```

---

## 7. Key Decisions & Rationale

1. **Lazy Supabase imports**: The `supabase` package isn't installable locally. `app/supabase.py` imports it lazily inside `_create_supabase_client()`, so all modules that import from it can be loaded and tested without the package.

2. **Hand-rolled CSS instead of Tailwind**: No `tailwindcss` dependency installed. `src/index.css` uses CSS variables for theming instead of Tailwind directives.

3. **No `package-lock.json`**: Committed intentionally (per .gitignore or omission). CI uses `npm install` instead of `npm ci`.

4. **gitleaks `|| true` equivalent in ruff**: CI uses `ruff check ... || true` so linting doesn't block CI while the codebase is being cleaned up.

5. **No ESLint config**: Added as a stretch goal. Frontend validation uses `tsc --noEmit` + `npm run build` only.

---

## 8. Notes for the Expert Reviewer

These are questions/decisions where external guidance would be valuable:

1. **Supabase client lifecycle**: Currently a module-level singleton. Should we use FastAPI's `lifespan` context for init/teardown? (The `main.py` lifespan is defined but may not fully manage the client.)

2. **Confidence threshold tuning**: The `CONFIDENCE_THRESHOLD = 0.7` and Gemini fallback at `< 0.7` — should these be configurable per-client or environment?

3. **Review queue resolution**: `resolve_review_item` currently only sets status to "approved"/"rejected". Should it also trigger invoice status updates (e.g., set invoice to "reviewed" or "auto_approved")?

4. **CSV export pagination**: `get_invoices()` returns ALL invoices. For large datasets (>1000), should we add pagination or server-side filtering?

5. **Digest time zones**: `generate_digest` uses `datetime.utcnow()` equivalent. Should digests respect the business's local timezone (IST)?

6. **Frontend health check resilience**: HealthGate polls every 2.5s. Should we add exponential backoff for production?

7. **OCR language support**: Currently English + Hindi. Should we add Marathi, Tamil, etc. for broader Indian market coverage?

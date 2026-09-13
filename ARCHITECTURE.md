# Invoxa - Architecture

## System Overview

```
User Browser -> Vercel Frontend -> Vercel Backend (serverless FastAPI) -> (OCR + regex OR Gemini API) -> Supabase
```

## Components

### Frontend (React + Vite on Vercel)
- **Upload.tsx**: Drag-drop zone, uploads directly to Supabase Storage via publishable key
- **ReviewQueue.tsx**: Lists flagged invoices, side-by-side view of extracted fields with confidence badges
- **Dashboard.tsx**: Stats, search/status/date filters, due-soon card, monthly trend (6M/12M), spend-by-category bars, weekly digest, bulk folder moves, Show-more pagination
- **HealthGate**: Checks backend /health before showing full UI; shows warm-up spinner during cold starts
- Uses `@supabase/supabase-js` with publishable key for Storage access only
- Calls backend API for extraction, review, export, digest endpoints

### Backend (Python + FastAPI on Vercel serverless)
- **app/main.py**: FastAPI app, health endpoint, lifespan management
- **app/config.py**: Environment variable loading (never logs secrets)
- **app/supabase.py**: Supabase client wrapper with service key
- **app/database.py**: Data access layer (invoices, vendors, review queue, corrections)
- **app/extraction/pipeline.py**: OCR-first extraction pipeline
- **app/api/**: FastAPI routers (auth, folders, invoices, review, export, digest, vendors, reports, account)
- **app/models/**: Pydantic data models
- **app/validation/**: GSTIN checksum, duplicate detection, anomaly checking
- **app/categorization/**: Gemini AI expense categorization (optional) with vendor-memory fallback
- **app/export/**: CSV, Excel (XLSX), Tally XML, PDF statement, GST summary, vendor summary PDF
- **app/digest/**: Weekly plain-English summary generation
- **app/review/**: Review queue logic, correction logging

### Data Layer (Supabase)
- **Postgres**: 7 tables (vendors, invoices, extraction_fields, review_queue, corrections, users, folders); migrations 0004-0006 add category, tax_amount and line_items columns to invoices
- **Storage**: 1GB free tier, invoices bucket for uploaded files

### Extraction Pipeline
1. PDF text-layer extraction via PyMuPDF (fitz) for speed
2. If no text layer, PyMuPDF renders pages to images at 300 DPI, Tesseract OCR with --oem 1 --psm 6
3. pdfplumber for layout-preserving table extraction from digital PDFs
4. Regex rules extract vendor, invoice number, amount, GSTIN, due date, line items
5. GSTIN validation via python-stdnum (official mod-36 Luhn checksum)
6. 5-strategy GSTIN candidate finder (structured regex, fuzzy OCR, positional context, checksum-only, numeric scan)
7. Arithmetic total validation (sum of line items + tax == Grand Total)
8. Confidence scoring per field (regex match + OCR word confidence + checksum validation)
9. If overall confidence < 0.7, fall back to Gemini 2.5 Flash vision API
10. Results stored in Supabase

### Regex Patterns
- GSTIN: `\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]`
- Invoice number: `(?:Invoice\s*(?:No|Number|#)\.?\s*[:−]?\s*)([\w\/\-]+)`
- Date: `(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4})`
- Amount: `(?:Grand\s*Total|Total|Amount)[^₹\d]{0,25}(?:Rs\.?|INR|₹)?\s*([\d,]+\.\d{0,2})`
- Taxes: `\b(CGST|SGST|IGST|UTGST)\b[^\₹\d\n]{0,30}(?:Rs\.?|INR|₹)?\s*([\d,]+\.\d{2})`
- Indian amounts use lakh grouping (e.g. ₹1,23,456.00) - strip commas before float conversion

### API Endpoints
- GET /health - warm-up endpoint
- POST /api/auth/signup | login, GET /api/auth/me - JWT sessions
- GET/POST /api/folders, PATCH/DELETE /api/folders/{id} - per-account folders
- POST /api/invoices/upload - multipart upload, extraction, auto categorization, vendor memory
- GET /api/invoices - list with folder/status/date-range/search filters
- GET /api/invoices/due-soon - unpaid invoices due within N days
- GET /api/invoices/{id} - detail with extraction fields and line items
- GET /api/invoices/{id}/file | /preview - receipt PDF stream / page-1 PNG
- PATCH /api/invoices/{id}/fields | /category | /folder; DELETE /api/invoices/{id}
- POST /api/invoices/{id}/extract | /correct - re-extraction, human correction
- GET /api/review/queue, POST /api/review/{id}/resolve | /{id}/correct
- GET /api/export/csv | xlsx | tally-xml | pdf | gst-summary | preview
- GET /api/vendors/summary | summary.pdf; GET /api/reports/monthly-spend | category-spend
- GET /api/digest - weekly summary (optional AI narrative)
- GET /api/account/export - full-account JSON download

## Deployment

Both services deploy to Vercel from one repository, configured by vercel.json:

- frontend — Vite, SPA rewrite for client-side routing
- backend — FastAPI serverless function (entrypoint backend/api/index.py, maxDuration 60s)

Routing: /api/* and /health reach the backend, everything else the frontend.
Secrets are Vercel project environment variables — nothing sensitive is
committed. render.yaml and backend/Dockerfile are legacy artifacts, unused
by this deployment. Serverless cold starts after idle are brief; the
frontend HealthGate shows a warm-up spinner while /health responds.

### Database Migrations
- Applied via Supabase Dashboard SQL editor or Supabase CLI
- Migrations: migrations/0001_init.sql (plus git-ignored 0002-0005 and 0006_line_items.sql; see README)

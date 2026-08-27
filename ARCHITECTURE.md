# Invoxa - Architecture

## System Overview

```
User Browser -> Vercel Frontend -> Render Python Backend -> (OCR + regex OR Gemini API) -> Supabase
```

## Components

### Frontend (React + Vite on Vercel)
- **Upload.tsx**: Drag-drop zone, uploads directly to Supabase Storage via publishable key
- **ReviewQueue.tsx**: Lists flagged invoices, side-by-side view of extracted fields with confidence badges
- **Dashboard.tsx**: Stats, CSV download, weekly digest
- **HealthGate**: Checks backend /health before showing full UI; shows warm-up spinner during cold starts
- Uses `@supabase/supabase-js` with publishable key for Storage access only
- Calls backend API for extraction, review, export, digest endpoints

### Backend (Python + FastAPI on Render)
- **app/main.py**: FastAPI app, health endpoint, lifespan management
- **app/config.py**: Environment variable loading (never logs secrets)
- **app/supabase.py**: Supabase client wrapper with service key
- **app/database.py**: Data access layer (invoices, vendors, review queue, corrections)
- **app/extraction/pipeline.py**: OCR-first extraction pipeline
- **app/api/**: FastAPI routers (invoices, review, export, digest)
- **app/models/**: Pydantic data models
- **app/validation/**: GSTIN checksum, duplicate detection, anomaly checking
- **app/categorization/**: Vendor-to-category rules, history lookup
- **app/export/**: CSV generation for Tally/Zoho
- **app/digest/**: Weekly plain-English summary generation
- **app/review/**: Review queue logic, correction logging

### Data Layer (Supabase)
- **Postgres**: 500MB free tier, 6 tables (vendors, invoices, extraction_fields, review_queue, corrections)
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
- POST /api/invoices - register invoice after file uploaded to Storage
- GET /api/invoices - list all invoices with status
- GET /api/invoices/{id} - single invoice detail with extraction fields
- POST /api/invoices/{id}/extract - trigger OCR extraction + validation
- POST /api/invoices/{id}/correct - save human correction
- GET /api/review/queue - list flagged invoices
- POST /api/review/{id}/resolve - mark as reviewed or auto-approved
- GET /api/export/csv - generate CSV for Tally/Zoho
- GET /api/digest - generate plain-English weekly summary

## Deployment

### Backend (Render Free Tier)
- 512MB RAM, 750 hrs/month (sleeps after 15 min idle)
- Dockerfile: python:3.12-slim + tesseract-ocr + tesseract-ocr-eng + tesseract-ocr-hin
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Cold start: 60-90s (mitigated by frontend warm-up spinner and optional cron-job.org keep-alive)

### Frontend (Vercel Hobby)
- Static site, always on
- No credit card required
- Non-commercial use only

### Database Migrations
- Applied via Supabase Dashboard SQL editor or Supabase CLI
- Migration file: migrations/0001_init.sql

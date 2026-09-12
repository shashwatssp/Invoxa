# Invoxa

**AI-powered invoice and accounts-payable automation for Indian micro-businesses.**

Upload a vendor invoice. In seconds, Invoxa reads it, extracts every field with a confidence score, checks it against your history, and either books it or hands it to you for a two-second review. At the end of the week you get a clean export for Tally or Zoho Books and a plain-English summary of where your money is going.

This is not meant to replace a finance team. It is meant to be the finance function for businesses that never had one.

---

## The problem

Indian micro and small enterprises (MSMEs) process invoices almost entirely by hand. A vendor invoice arrives as a PDF, a WhatsApp photo, a scan, or an email attachment — in no standard format — and someone has to read it, retype the numbers into Excel or Tally, check it isn't a duplicate, and decide which expense category it belongs to.

The scale of the problem, per Razorpay's "Fix My Itch" research:

| Metric | Value |
| --- | --- |
| Companies still doing manual invoice processing | 78% |
| Cost per invoice (manual) | ₹150–300 |
| Time to process one invoice end-to-end | 5–15 days |
| Manual data-entry error rate (normal load) | 1–4% |
| Manual data-entry error rate (high load) | 18–40% |
| Share of all invoice errors caused by manual entry | 60%+ |
| Addressable MSMEs in India | 63.4 million (63.1M are 1–10 employee "micro" businesses) |

The root cause, in three parts:

1. **No standard invoice format** — every vendor sends invoices differently.
2. **No dedicated finance headcount** — a 5-person shop has no accountant checking every line.
3. **Existing AP automation is built for enterprises** — priced and designed for teams processing 10,000+ invoices/month, not a shop processing 50.

The manual process isn't just slow — it's also not actually accurate. It's unaudited risk that happens to be invisible because no one is measuring it.

## What we're building

A small business owner (or their one bookkeeper) receives a vendor invoice — a courier receipt photographed on WhatsApp, or a raw-materials supplier's PDF emailed over. Today, that invoice sits in a folder or inbox until someone manually opens it, reads it, and types it into Tally.

With Invoxa:

1. They upload the invoice to their dashboard.
2. Within seconds, the extraction pipeline reads the document and pulls out the vendor name, invoice number, amount, GST number, due date, and line items — each field tagged with a confidence score.
3. The system independently checks: is the GST number valid? Have we seen this exact vendor + number + amount combination before (possible duplicate)? Do the line items actually add up to the total?
4. If everything is clean and high-confidence, the invoice flows straight through. If anything is uncertain, duplicate-flagged, or inconsistent, it's routed to a human review queue — never silently pushed forward.
5. Receipts can be organized into **folders** (per client, project, or shop) at upload time, browsed with one-tap filters, and exported per folder.
6. The owner opens the **Export Center**, picks a format (CSV, Excel, Tally XML, or a printable PDF statement), a period (last 7/14 days, this month, last month, any custom number of days/weeks/months, or everything), a folder, or a hand-picked selection of invoices — sees a live preview of what's inside — and downloads it. Plus a plain-English weekly summary: "₹84,200 payable this week, 41 invoices processed automatically, 3 flagged for your review."

## How accuracy is ensured

A tool that silently mis-enters a number into someone's books is worse than no tool at all. Invoxa leans on four independent layers rather than trusting the model to be right:

- **Confidence scoring on every field.** Extraction isn't a black box — every value (vendor, amount, GST number, dates) carries a confidence score derived from how it was found: checksum-validated GSTINs and labeled amounts score higher than loose regex hits. Clean invoices score 85–95% and auto-approve; anything below 80% or with a failed validation is flagged, never silently accepted.
- **Rule-based validation, not just AI judgment.** GST numbers are checked against India's actual GSTIN checksum algorithm — a deterministic, non-AI check that either passes or fails. Line items must arithmetically reconcile with the invoice total within a stated tolerance.
- **Cross-referencing against history.** Duplicate detection (same vendor + invoice number + amount) acts as a second, independent error-catching layer that doesn't depend on the extraction being perfect in the first place.
- **Continuous measurement.** Every time a human corrects a field, that correction is logged. Over time this produces a real, measured accuracy rate — not a marketing claim — with a target of a sub-1% effective error rate once human review is factored in.

The honest framing: the AI won't be 100% accurate at extraction. The system is designed so it doesn't need to be — it needs to know when it might be wrong and hand that specific case to a person.

## Where humans stay in the loop

Human involvement is deliberately placed at the points where mistakes are expensive, not distributed evenly across the whole process:

- **Review queue for flagged items only** — low-confidence extractions, potential duplicates, and amounts that don't reconcile land in front of a person. Clean, high-confidence invoices never require a human touch.
- **Side-by-side verification** — the original receipt renders right next to the extracted data (page-1 thumbnails in the queue, full document in the viewer), so a human can visually confirm a field in about two seconds rather than re-reading the whole document.
- **No financial action is ever auto-executed.** The agent extracts and flags — it does not pay, file, or submit anything on its own. A human approves before anything touches payments, exports, or filings.
- **Approval is loud, not silent.** Approving (or correcting) an invoice removes it from the queue with a visible confirmation, marks it "reviewed" across the dashboard, digest, and exports immediately — so the books reflect the decision the moment it's made.
- **Correction tracking** — every human edit is persisted, feeding the measured-accuracy loop.

In short: the AI does the reading and the first pass of judgment; the human does the final call on anything uncertain or consequential.

## Time savings for end users

Based on typical volumes for a small Indian business (50–200 invoices/month) and a manual processing time of roughly 5–10 minutes per invoice:

| Business size | Invoices/month | Manual time/month | With Invoxa | Time saved |
| --- | --- | --- | --- | --- |
| Small | 50 | ~4–8 hours | ~30–60 min | ~85–90% |
| Mid | 150 | ~12–25 hours | ~1.5–3 hours | ~85–90% |
| Larger micro-SME | 600 | ~50–100 hours | ~6–10 hours | ~85–90% |

The realistic promise: a business that spends a full workday a week on invoices should be able to get that down to under an hour, with the remaining time spent only on the handful of items the system flagged as genuinely needing a human eye.

## The benefit

- **Time back** — hours per week returned to the owner or bookkeeper, who is usually doing this on top of an actual job, not as their job.
- **Fewer costly mistakes** — duplicate payments and mis-entered amounts caught before they become a bank transfer, not after.
- **Books that are actually current** — instead of a shoebox of invoices reconciled once a quarter under deadline pressure, invoices flow into Tally/Zoho continuously.
- **Visibility without a finance hire** — the weekly plain-English digest gives an owner a cash-flow snapshot they'd otherwise only get by asking an accountant.
- **Priced for the business it's actually built for** — free for the smallest shops (up to 20 invoices/month), scaling to a few thousand rupees a month rather than an enterprise contract.

## Where this sits in the market

AI-powered invoice and AP automation is an active, fairly crowded category — but it is underserved at the specific size and price point Invoxa targets.

- **Global / enterprise-oriented players** (BILL, Stampli, Tipalti, Vic.ai, Medius) offer mature AP automation, but they're built and priced for mid-market to enterprise finance teams — the opposite of the messy, low-volume, no-finance-team reality of a 5-person Indian shop.
- **India-focused AP/spend platforms** (Mysa, RazorpayX, EnKash, Volopay) serve the Indian startup/SME market, but several require a minimum monthly transaction volume (around ₹10 lakh/month) to unlock full value, which puts them out of reach for genuinely micro businesses.
- **India-specific GST-native tools** (such as Plyndrox Payable AI) target the same underserved segment, accepting PDFs, images, and Gmail attachments with GSTIN and GST-breakdown extraction.

What's genuinely differentiated in Invoxa, versus most of the above:

1. **Confidence-scored extraction with visible flagging**, rather than a black-box "trust the OCR" approach — epistemic honesty about uncertainty as a first-class feature.
2. **A hard rule that no financial action is ever auto-executed** — a design constraint, not a configurable setting, which matters for a business owner with no finance team to catch a runaway automation.
3. **A free tier genuinely usable for the smallest shops** (20 invoices/month) rather than a free-trial funnel.
4. **Built around India's actual invoice chaos** — WhatsApp photos, scans, and every layout under the sun — and around Tally, which remains the dominant bookkeeping tool for this segment.

The category is proven and competitive; the specific combination of (a) true micro-SME pricing, (b) GST/Tally-native design, and (c) a human-in-the-loop accuracy model built as a first-class feature rather than an afterthought is the actual differentiation — not the underlying idea of "AI reads your invoices."

## Architecture

A two-service deployment on Vercel, backed by Supabase:

| Layer | Technology | Notes |
| --- | --- | --- |
| Frontend | React + Vite + TypeScript | Mobile-first design system, no UI framework; pdf.js receipt viewing |
| Backend | FastAPI (Python 3.12) | Serverless on Vercel; all routes authenticated with JWT |
| Database | Supabase (Postgres + Storage) | Invoices, folders, vendors, users, extraction fields, review queue, corrections |
| Extraction | PyMuPDF, pdfplumber, pytesseract (optional), Gemini fallback | Evidence-weighted confidence scoring; text-layer first, OCR for scans |

### Extraction pipeline

1. Text-layer extraction (pdfplumber, then PyMuPDF), falling back to Tesseract OCR for scanned documents.
2. Regex rules tuned per layout family: Indian GST, international (USD/EUR/CHF), delivery notes, airline breakdowns.
3. Evidence-weighted per-field confidence: GSTIN checksum validation, labeled vs. derived amounts, arithmetic consistency (subtotal + tax = total).
4. Validation: GSTIN checksum, duplicate detection, line-item reconciliation, date sanity.
5. Auto-approve at 80%+ overall confidence with no anomalies; otherwise queue for review with a human-readable reason.
6. Gemini vision fallback for very-low-confidence documents when an API key is configured.

### Export Center

One dialog, every format, any slice of the books — modal on desktop, bottom sheet on mobile, with a live preview ("42 invoices · ₹1,23,456") before download:

- **CSV** — Tally/Zoho-compatible column layout.
- **Excel (XLSX)** — native import into Zoho Books, Excel, and Google Sheets.
- **Tally XML** — Purchase vouchers ready for Gateway of Tally > Import > XML.
- **PDF statement** — clean printable A4 statement (per-page running totals) for printing or emailing to a CA.

Every export accepts the same optional scope: a **period** (last 7 or 14 days, this or last month, any custom number of days/weeks/months, or everything), a **status** (auto-approved, reviewed, or all), a **folder**, or a hand-picked **selection of invoices** from the dashboard. All exports stay scoped to the logged-in account.

### Folders

Uploads can be filed into flat, per-account folders (per client, project, or shop) — chosen once per scanning batch, filtered with one tap on the dashboard, and used as an export scope. Deleting a folder never deletes invoices; they fall back to "No folder" at the database level.

## Developer quickstart

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

Environment variables (copy `.env.example` to `.env` at the repo root):

```
SUPABASE_URL=...
SUPABASE_PUBLISHABLE_KEY=...
SUPABASE_SERVICE_KEY=...
SECRET_KEY=<random 64-hex string; required for stable JWT sessions>
GEMINI_API_KEY=...          # optional, enables the vision fallback
DATABASE_URL=...            # optional, for CLI migrations
```

Apply migrations in your Supabase SQL editor: `migrations/0001_init.sql`, then `migrations/0002_auth.sql` and `migrations/0003_folders.sql` (kept out of the repo — see `.gitignore`; apply with `python scripts/apply_0003.py` or by hand).

### Frontend

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173, API proxied to :8000
```

### Tests

```bash
cd backend && python -m pytest tests -q          # 170+ unit/integration tests
python -m ruff check backend                     # lint
cd frontend && npm run typecheck && npm run build
```

### End-to-end validation

```bash
cd backend/test-assets
INVOXA_BASE_URL=https://your-deployment.vercel.app python run_e2e.py
```

Signs up two accounts, uploads every test PDF, asserts ground-truth fields, verifies per-account data isolation (invoices, folders, review queue, digest), ownership enforcement on receipts and previews, the review workflow (including approval syncing the invoice status to "reviewed"), duplicate detection, folder-scoped and period-filtered exports (CSV by id, PDF statement), and the digest.

### Deployment

Vercel Services deploys both halves from one repo, one domain:

- `frontend` — Vite, SPA rewrite for client-side routing.
- `backend` — FastAPI, entrypoint `api/index.py`, function timeout raised to 60s for extraction.

`vercel.json` at the repo root owns all public routing: `/api/*` and `/health` reach the backend, everything else the frontend. Secrets are configured as project environment variables — nothing sensitive is committed.

## License

Proprietary — all rights reserved.

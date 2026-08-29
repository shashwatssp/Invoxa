# Invoxa

**The finance function for businesses that never had one.**

Invoxa reads vendor invoices — a WhatsApp photo, a scanned PDF, an email
attachment, whatever form it arrives in — and turns them into clean,
categorized, Tally/Zoho-ready records, catching the duplicates and mistakes
a human would miss on a Tuesday afternoon with forty other things to do.

---

## The problem

78% of Indian MSMEs still process invoices by hand. A vendor invoice lands
in a folder or an inbox, and someone — usually the owner, not an
accountant, because a 5-person shop doesn't have one — has to open it, read
it, and retype the numbers into Excel or Tally.

That process is slow and it is not actually accurate, even though the
inaccuracy is mostly invisible because nobody is measuring it:

| Metric | Value |
|---|---|
| Cost per invoice, manual processing | ₹150–300 |
| Time to process one invoice, end to end | 5–15 days |
| Manual data-entry error rate, normal load | 1–4% |
| Manual data-entry error rate, high load | 18–40% |
| Share of all invoice errors from manual entry | 60%+ |
| Addressable MSMEs in India | 63.4 million |

Three things cause this, and none of them are the business owner's fault:

1. **No standard invoice format.** Every vendor sends invoices differently.
2. **No dedicated finance headcount.** There's no accountant checking every
   line before it goes into the books.
3. **Existing AP automation is built for enterprises.** It's priced and
   designed for teams processing 10,000+ invoices a month, not a shop
   processing 50.

This isn't a tooling gap so much as a size gap — the tools that exist assume
a finance team that this segment doesn't have.

---

## What Invoxa does

1. Upload the invoice (or forward it) to the dashboard.
2. The extraction pipeline reads it — trying the fast path first (native PDF
   text layer, then OCR for scans and photos), pulling out vendor name,
   invoice number, amount, GSTIN, due date, and line items, each field
   tagged with a confidence score.
3. If confidence is too low for the fast path to trust itself, the invoice
   goes to a vision-LLM fallback instead of guessing.
4. Independent checks run regardless of extraction method: is the GSTIN
   checksum valid? Have we seen this vendor + amount + date combination
   before (possible duplicate)? Does this amount look unusual for this
   vendor's history (possible anomaly)?
5. Clean, high-confidence invoices flow straight through. Anything flagged
   — low confidence, a possible duplicate, an anomaly — goes to a human
   review queue instead of being silently pushed forward.
6. The owner gets a CSV they can import into Tally or Zoho Books, and a
   plain-English weekly digest: *"₹84,200 payable this week, 41 invoices
   processed automatically, 3 flagged for your review."

Invoxa isn't trying to replace a finance team. It's trying to be the finance
function for the businesses that never had one.

---

## Why this is trustworthy, not just automated

A tool that silently mis-enters a number into someone's books is worse than
no tool at all. Invoxa leans on layered, independent checks rather than
trusting any single extraction to be right:

- **OCR and regex extraction first**, with structured rules for GSTIN,
  amounts, and dates — deterministic where deterministic is possible,
  rather than sending every invoice to an LLM by default.
- **A vision-LLM fallback**, used only when confidence is genuinely low —
  which keeps it cheap enough to run on a free API tier and keeps the
  primary path auditable.
- **Rule-based validation that doesn't depend on the AI being right** — the
  GSTIN checksum either passes or fails; duplicate and anomaly detection
  compare against real history, independent of how the extraction happened.
- **Confidence scores on every field**, visibly flagged, never silently
  accepted.
- **Every human correction is logged**, which turns "we think it's
  accurate" into a real, measured number over time instead of a marketing
  claim.
- **No financial action is ever auto-executed.** Invoxa extracts and flags.
  A human approves before anything touches an export or a filing.

---

## Architecture

```
Browser → Frontend (Vercel/Netlify) → Backend API (Render, FastAPI)
                                            │
                              OCR + regex ──┼── Gemini 2.5 Flash (fallback only)
                                            │
                                       Supabase (Postgres + Storage)
```

| Layer | Tech |
|---|---|
| Backend | Python 3.12 + FastAPI, hosted on Render (free tier) |
| Frontend | React 18 + Vite 5 + TypeScript, hosted on Vercel/Netlify |
| Data | Supabase Postgres + Storage |
| OCR | Tesseract 5, PyMuPDF, pdfplumber |
| Validation | python-stdnum (GSTIN mod-36) + custom anomaly/duplicate checks |
| Fallback extraction | Gemini 2.5 Flash |
| Secret scanning | gitleaks, pre-commit + CI |

The free-tier backend sleeps when idle. The frontend calls `/health` on
load and shows a short "waking up" state instead of letting the first real
request time out — this is why `/health` exists as its own endpoint rather
than being folded into another route.

---

## Current status

14 sprints built: schema and migrations, OCR-first extraction pipeline with
GSTIN/anomaly/duplicate validation, FastAPI endpoints, the review queue with
correction logging, CSV export for Tally/Zoho, weekly digest generation,
CI with secret scanning, and the React frontend (upload, review queue,
dashboard). 117 backend tests passing.

See `ARCHITECTURE.md` for the full design and `AUDIT_LOG.md` for the
build's decision history.

---

## Getting started

```bash
git clone <repo-url>
cd invoxa
cp .env.example .env   # fill in Supabase and Gemini keys — never commit .env
docker compose up      # local Postgres + services
```

Frontend and backend run separately in dev — see `frontend/README.md` and
`backend/README.md` for service-specific setup once those exist.

---

## Roadmap

Near-term priorities: reproducible CI (commit the frontend lockfile, make
lint actually fail the build), IST-correct digest boundaries, and wiring
review resolution through to invoice status. Longer-term: additional Indian
language OCR support once real usage shows which languages actually appear
in flagged invoices, Excel/JSON export, and an automated email digest.

## License

MIT License

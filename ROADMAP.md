# Invoxa — Product Roadmap

> Living roadmap. Last aligned to repo state: Sep 17, 2026 (`progress.md`, 310 tests passing).
> Owner: Shashwat (solo build). Constraint: zero third-party spend — Gemini API key + free-tier infra only (Supabase, Vercel).

---

## 0. Where the project actually stands today

Read directly from the repo, not aspirational:

- **Live**: `invoxa4u.vercel.app`, two-service deployment (Vite frontend + FastAPI backend) on Vercel, Supabase Postgres + Storage.
- **Extraction pipeline**: OCR-first (PyMuPDF → Tesseract fallback), regex rules per layout family, 5-strategy GSTIN finder, arithmetic validation, confidence scoring, Gemini 2.5 Flash vision fallback below 0.7 confidence — now with correction-learning few-shot hints from the account's own review history.
- **Validation**: GSTIN mod-36 checksum, 6 anomaly types, duplicate detection.
- **Review loop**: flagged-item queue, correction logging with full audit trail, human approval required before anything is "final."
- **AI & agent layer (new)**: bounded read-only "Ask Invoxa" agent (natural-language Q&A over whitelisted account-scoped queries), AI flag explanations in the review queue, payment-chase reminder drafts (draft-only, prefilled `wa.me` links, never auto-sent), weekly digest email (stdlib SMTP).
- **Hardening (new)**: per-account sliding-window rate limits on AI-costly endpoints, upload file-type gate (PDF/images only), digest clock on IST, stdlib logging setup, ESLint as a blocking CI gate.
- **Exports**: CSV (Tally/Zoho column layout), XLSX, Tally XML, GST summary.
- **Extras already shipped**: Gemini-based auto expense categorization, editable fields with audit, vendor view with WhatsApp/PDF share, due-soon card, 6M/12M trend + category spend, GST summary export, PWA with share-target ingestion, line items, vendor memory, data export, pagination, dark mode.
- **Tests**: 310 passing, 1 skipped. CI runs backend lint + frontend lint + frontend type-check + build + gitleaks secret scan — all blocking.
- **Known gaps (open)**: no frontend unit tests yet (Vitest + RTL), Supabase client still a module-level singleton (lifespan managed), agent budget/audit tables (migration `0007`) must be applied in Supabase before the daily accounting is active (the agent degrades gracefully without them).

---

## Guiding principles for every phase

1. **No financial action is ever auto-executed.** This is a hard product rule, not a toggle — it stays true through every new feature below. The agent layer is read-only by construction; drafts and reminders wait for a human click.
2. **Zero recurring cost.** Every capability runs on the Gemini free tier + free-tier Supabase/Vercel. Anything requiring a paid API (GSP for GST data, WhatsApp Business API, credit-bureau data) is deferred or replaced with a free-equivalent approach.
3. **Human-in-the-loop stays the differentiator.** New modules follow the same pattern as invoice extraction: confidence-scored where relevant, flagged where uncertain, never silently trusted.
4. **Ship in the order that de-risks the business, not the order that's most fun to build.**

---

## Phase 1 — Stabilization & Production Hardening — ✅ DONE (Sep 14)

Shipped: rate limiting on upload/extract/agent endpoints (`RATE_LIMIT_<BUCKET>_PER_HOUR`), upload file-type validation, IST digest clock, stdlib logging, ESLint config + blocking CI step. (conftest.py, blocking ruff, requirements-dev.txt were already in place from earlier sprints; the Makefile was consciously dropped — Windows/PowerShell shop.)

---

## Phase 1b — AI & Agent Foundation — ✅ DONE (Sep 15–16)

- **Bounded tool-use loop** (`app/agent/loop.py`): max 8 tool rounds / 10 model calls per run, daily Gemini budget (~240 calls/day, resets midnight IST, tracked in `gemini_usage`), append-only `agent_audit` trail. Any AI failure degrades gracefully — the rest of the product is never touched.
- **Ask Invoxa** (`/app/ask`): natural-language questions over 8 whitelisted, account-scoped, read-only queries (overview, due soon, vendor/category/monthly spend, flagged, search, GST summary). Intent-based function calling — deliberately not raw text-to-SQL.
- **Flag explanations** (review queue): one call per request explaining what to verify before approving.
- **Payment-chase drafts**: due/overdue grouped by vendor, drafted WhatsApp reminder + prefilled `wa.me` link. Draft-only; template fallback when AI is off.
- **Correction-learning**: recent human corrections feed the fallback prompt as few-shot hints.
- **Digest email** (`POST /api/digest/email`): stdlib SMTP, Gmail app password compatible, reports cleanly when unconfigured, rate limited to 10/hour.

---

## Phase 2 — GST Reconciliation Module — NEXT UP

**Goal:** extend Invoxa from "read my invoices" to "tell me what doesn't match between my invoices and what the government has on record." Same user, same data model, genuinely new value.

### 2.1 Data ingestion (free-tier workaround)
There is no free bulk GSTR-2A/2B API — official access requires paid GSP registration. The workaround: GSTR-2A/2B is a routine monthly download every filing business already does from the GST portal (JSON or Excel). Invoxa needs only a file upload.
- New upload flow: "Upload GSTR-2A/2B" (JSON and XLSX parsers — `openpyxl` already a dependency)
- Parse into a `gst_return_records` table (GSTIN, invoice number, date, taxable value, tax amount, filing period)

### 2.2 Reconciliation engine (rule-based, no LLM cost)
- Match `invoices` against `gst_return_records` on GSTIN + invoice number + amount, with fuzzy matching for OCR noise (`rapidfuzz`, MIT-licensed, pure Python)
- Three-way match status per invoice: **Matched**, **Amount mismatch**, **Missing in GSTR-2A/2B** (vendor hasn't filed — a real, common, costly ITC problem for MSMEs)
- Store match status + delta on the invoice record, surfaced in the existing dashboard

### 2.3 Gemini's role — kept deliberately small
- Plain-English reconciliation summary ("3 vendors haven't filed 7 of your invoices — ₹42,000 in ITC at risk this period")
- Draft text for vendor follow-ups (reuses the chase-draft pattern)
- Roughly one call per reconciliation run, not one per invoice.

### 2.4 Data model additions
```
gst_return_records: id, business_id, gstin, invoice_number, filing_period,
                     taxable_value, tax_amount, source_file, uploaded_at

reconciliation_matches: id, invoice_id, gst_record_id, match_status,
                         amount_delta, matched_at
```

**Exit criteria:** a user can upload their monthly 2A/2B file and get a reconciliation report with actionable, one-click vendor follow-ups — zero new recurring cost.

---

## Phase 3 — Vendor Payment Intelligence

**Goal:** turn payment history already in Invoxa into a decision-support signal, without touching paid credit-bureau data. Starts only after Phase 2 (the score consumes reconciliation data).

- **Internal vendor risk score** from data Invoxa legitimately holds: days-to-pay trend, late-payment frequency, filing consistency (does this vendor's invoice actually appear in GSTR-2A reliably?)
- Surface as a per-vendor badge in the existing vendor view, not a new page
- Explicitly out of scope: external credit bureau lookups, scraped GST-portal compliance status

---

## Phase 4 — Frontend & UX Polish (can run partly parallel to Phase 2/3)

- Frontend unit tests (Vitest + React Testing Library) — currently zero
- Error boundaries in React components; loading states for all API calls
- tsconfig strict-mode cleanup

---

## Phase 5 — Launch Readiness

- Complete `ARCHITECTURE.md` with a real deployment diagram
- Decide whether `render.yaml` + `backend/Dockerfile` stay as dead weight
- Enforce the pricing/tier boundary in code (README states "free up to 20 invoices/month") before real users arrive
- Basic security headers (`X-Content-Type-Options`, `X-Frame-Options`)
- Keep `origin/master` in sync with local `master` as part of the routine

---

## Phase 6 — Stretch Goals (post-launch, prioritize by user feedback)

1. **Batch invoice processing** — upload many at once
2. **Multi-language OCR** — Hindi already supported; Tamil/Telugu/Kannada next, prioritized by where early users are
3. **GST reconciliation agent** — once Phase 2 ships, the existing agent loop gets reconciliation as just another tool
4. **Automated weekly digest schedule** — the email mechanism exists; add a scheduled trigger

---

## Suggested sequencing

```
Phase 2 (GST reconciliation) → Phase 3 (vendor risk)
            ↘ Phase 4 (polish, parallel) ↙
                   Phase 5 (launch)
                          ↓
                   Phase 6 (stretch)
```

---

## What's explicitly out of scope (and why)

| Idea | Why it's excluded |
|------|---------------------|
| Live GSTIN compliance/default lookups | No free bulk API; scraping the GST portal violates its ToS and is fragile |
| WhatsApp Business API or unofficial automation libraries | Paid, or ToS/ban risk respectively — `wa.me` links cover the real need for free |
| External credit bureau data (CIBIL-style) | Paid, and unnecessary — internal payment-history scoring covers the core value |
| Raw text-to-SQL for the agent | Injection/escalation risk; intent-based function calling covers the same need safely |
| Multi-user/shared workspace | Deliberate product decision already made — Invoxa stays single-account by design |
| Auto-sent payments, filings, or reminders | Permanent product rule — humans click every consequential button |

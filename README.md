# Invoxa

AI-powered invoice and accounts payable automation for Indian micro-SMEs.

## Overview

Invoxa automates invoice processing using an OCR-first, rules-based pipeline:
- **Digital PDFs (text layer):** pdfplumber + regex rules, zero LLM calls
- **Scanned PDFs (image only):** Tesseract OCR + same regex rules
- **Low confidence (<0.7):** Gemini vision API as fallback only

Target accuracy: 90-99% effective, with Gemini API usage well below the 250/day free tier limit.

## Tech Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.12 + FastAPI on Render (free tier) |
| Frontend | React 18 + Vite 5 + TypeScript + Shadcn UI on Vercel (Hobby) |
| Data Layer | Supabase Postgres + Storage |
| OCR | Tesseract 5 (--oem 1, --psm 6) + PyMuPDF + pdfplumber |
| Validation | python-stdnum (GSTIN mod-36 checksum) + bharatutils (INR formatting) |
| Fallback LLM | Gemini 2.5 Flash (~250 req/day free) |
| Secret Scanning | gitleaks (pre-commit + CI) |

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 18+
- Git

### Local Development

1. Clone and install dependencies:
```bash
git clone https://github.com/shashwatssp/Invoxa.git
cd Invoxa
pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
```

2. Create `.env` from `.env.example` and fill in your Supabase/Gemini credentials.

3. Start local services:
```bash
docker-compose up
```

4. Run backend locally (without Docker):
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

5. Run frontend locally:
```bash
cd frontend
npm run dev
```

### Pre-commit Hooks

Install the pre-commit framework and hooks (includes gitleaks secret scanning):
```bash
pip install pre-commit
pre-commit install
```

### Environment Variables

Copy `.env.example` to `.env` and fill in values:

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_PUBLISHABLE_KEY` | Supabase publishable (anon) key |
| `SUPABASE_SERVICE_KEY` | Supabase service role key (backend only) |
| `GEMINI_API_KEY` | Google Gemini API key (fallback only) |
| `DATABASE_URL` | Supabase connection string (for CLI migrations) |

Frontend environment (configure on Vercel):
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_PUBLISHABLE_KEY`
- `VITE_API_BASE_URL` (backend URL on Render)

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design.

## License

MIT

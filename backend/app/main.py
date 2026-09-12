from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError as PostgrestAPIError

from app.api.auth import router as auth_router
from app.api.digest import router as digest_router
from app.api.export import router as export_router
from app.api.folders import router as folders_router
from app.api.invoices import router as invoices_router
from app.api.review import router as review_router
from app.supabase import close_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Supabase client is created lazily on first request
    yield
    # Shutdown: clean up Supabase session
    close_client()


app = FastAPI(
    title="Invoxa API",
    description="AI-powered invoice automation for Indian micro-SMEs",
    version="0.1.0",
    lifespan=lifespan,
)

# Allow the frontend (local dev on port 5173, or any production host) to call
# the API directly. In dev the frontend sets VITE_API_BASE_URL=http://localhost:8000,
# which is a cross-origin request, so we must permit it here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers (auth first; the rest are protected via dependencies)
app.include_router(auth_router)
app.include_router(folders_router)
app.include_router(invoices_router)
app.include_router(review_router)
app.include_router(export_router)
app.include_router(digest_router)


@app.exception_handler(PostgrestAPIError)
async def _postgrest_api_error_handler(request, exc: PostgrestAPIError):
    """Return clean JSON for PostgREST errors.

    PGRST205 ("table not found") occurs when the Supabase migrations haven't
    been applied yet. Surface an actionable message instead of a raw 500.
    """
    if getattr(exc, "code", None) == "PGRST205":
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    "Database table not found (PGRST205). Apply migrations/0001_init.sql "
                    "in your Supabase SQL editor, then restart the backend."
                )
            },
        )
    return JSONResponse(status_code=500, content={"detail": f"Database error: {exc}"})


@app.get("/health")
async def health():
    return {"status": "ok"}

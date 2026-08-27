from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.supabase import close_client
from app.api.invoices import router as invoices_router
from app.api.review import router as review_router
from app.api.export import router as export_router
from app.api.digest import router as digest_router


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

# Include API routers
app.include_router(invoices_router)
app.include_router(review_router)
app.include_router(export_router)
app.include_router(digest_router)


@app.get("/health")
async def health():
    return {"status": "ok"}

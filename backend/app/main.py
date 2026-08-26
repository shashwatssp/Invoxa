from fastapi import FastAPI
from contextlib import asynccontextmanager

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


@app.get("/health")
async def health():
    return {"status": "ok"}

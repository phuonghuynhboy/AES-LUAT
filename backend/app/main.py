"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes.chat import router as chat_router
from .api.routes.health import router as health_router
from .core.config import cors_origins

app = FastAPI(
    title="AES LUẬT API",
    version="0.1.0",
    description="HTTP adapter for the existing Vietnamese legal RAG pipeline.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.include_router(health_router)
app.include_router(chat_router)

"""
main.py - server entry point
To add a new router: import it then add one app.include_router() line
"""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from database import init_db
from seed_data import seed

# ── routers ──────────────────────────────────────────────
from routers import pest as pest_router
from routers import knowledge as knowledge_router
from routers import analysis as analysis_router
from routers import report as report_router

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB and seed data on startup"""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}...")
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
    await init_db()
    await seed()
    logger.info("Server ready!")
    yield
    logger.info("Server stopped")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## Fly Analyzer API

Upload a photo to identify fly species and generate a pest control report.

### Priority rule
- HIGH priority: user-input field knowledge
- LOW priority: literature-based defaults
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

# ── register routers (add one line per new router) ───────
app.include_router(pest_router.router)
app.include_router(knowledge_router.router)
app.include_router(analysis_router.router)
app.include_router(report_router.router)


@app.get("/", tags=["System"])
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)

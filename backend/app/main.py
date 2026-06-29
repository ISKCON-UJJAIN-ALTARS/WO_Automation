import logging
import sys
import os
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# Load .env before anything else imports os.environ-based config
# (sheets_service.py reads GOOGLE_SHEETS_* at import time).
load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.routes.templates import router as templates_router

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Divine Sky Work Order API started successfully.")
    yield


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Divine Sky – Work Order Automation API",
    description=(
        "Accepts altar dimensions, writes them into a Google Sheet, "
        "reads calculated outputs, and renders a dimensioned template image."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS: allow the configured frontend origin(s) to call this API ───────────
# ALLOWED_ORIGINS is a comma-separated list, e.g.:
#   "http://localhost:5173,https://your-project.vercel.app"
# Defaults to just the local Vite dev server if unset.
_allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173")
_allowed_origins = [origin.strip() for origin in _allowed_origins_env.split(",") if origin.strip()]
logger.info("CORS allowed origins: %s", _allowed_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files: serve generated images under /generated ────────────────────
_GENERATED_DIR = Path(__file__).resolve().parents[1] / "generated"
_GENERATED_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/generated", StaticFiles(directory=str(_GENERATED_DIR)), name="generated")

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(templates_router, tags=["Work Orders"])


@app.get("/", include_in_schema=False)
def root():
    return {"message": "Divine Sky Work Order API is running. Visit /docs for the Swagger UI."}
@app.get("/health/", include_in_schema=False)
def health():
    return {"message": "Divine Sky Work Order API is healthy."}
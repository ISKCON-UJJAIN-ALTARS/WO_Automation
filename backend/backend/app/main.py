import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes.templates import router as templates_router

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Divine Sky – Work Order Automation API",
    description=(
        "Accepts altar dimensions, writes them into an Excel workbook, "
        "reads calculated outputs, and renders a dimensioned template image."
    ),
    version="1.0.0",
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


@app.on_event("startup")
def on_startup():
    logger.info("Divine Sky Work Order API started successfully.")

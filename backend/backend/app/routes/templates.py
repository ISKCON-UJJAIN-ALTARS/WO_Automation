import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.schemas.request_models import GenerateRequest, GenerateResponse
from app.services.excel_service import write_inputs_and_read_outputs
from app.services.template_service import render_template

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Load mappings config once at import time ──────────────────────────────────
_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "template_mappings.json"

with _CONFIG_PATH.open() as fh:
    _TEMPLATE_CONFIG: dict = json.load(fh)

# Base directory of the project (backend/)
_BASE_DIR = Path(__file__).resolve().parents[3]


@router.post("/generate", response_model=GenerateResponse, summary="Generate work-order image")
def generate_work_order(request: GenerateRequest):
    """
    Accepts altar dimensions, writes them into Excel, reads calculated outputs,
    detects placeholders in the template image, replaces them with real values,
    and returns the path of the generated PNG.
    """
    template_key = request.template

    # ── Validate template key ─────────────────────────────────────────────────
    if template_key not in _TEMPLATE_CONFIG:
        available = list(_TEMPLATE_CONFIG.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Template '{template_key}' not found. Available templates: {available}",
        )

    cfg = _TEMPLATE_CONFIG[template_key]

    # ── Step 1: Write inputs → read outputs via Excel ─────────────────────────
    logger.info("Processing template '%s' with inputs: %s", template_key, request.inputs)

    try:
        output_values = write_inputs_and_read_outputs(
            inputs=request.inputs.model_dump(),
            input_mappings=cfg["input_mappings"],
            output_mappings=cfg["output_mappings"],
            input_sheet=cfg["input_sheet"],
            output_sheet=cfg["output_sheet"],
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error in Excel service")
        raise HTTPException(status_code=500, detail=f"Excel processing error: {exc}")

    logger.info("Excel outputs: %s", output_values)

    # ── Step 2: Render template image ─────────────────────────────────────────
    template_rel_path = cfg["template_image"]           # e.g. "templates/4dome_ceiling.png"
    template_abs_path = _BASE_DIR / template_rel_path

    try:
        output_path = render_template(template_abs_path, output_values)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error in template service")
        raise HTTPException(status_code=500, detail=f"Image rendering error: {exc}")

    # Return a relative-style path for the response body
    relative_output = "/" + str(output_path.relative_to(_BASE_DIR))

    return GenerateResponse(
        success=True,
        image_path=relative_output,
        values=output_values,
    )


@router.get("/generate/download", summary="Download the latest generated image")
def download_generated_image(filename: str):
    """
    Download a previously generated image by filename.
    Example: GET /generate/download?filename=4dome_ceiling_1234567890.png
    """
    generated_dir = _BASE_DIR / "generated"
    file_path = generated_dir / filename

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found in generated/")

    return FileResponse(
        path=str(file_path),
        media_type="image/png",
        filename=filename,
    )


@router.get("/templates", summary="List available templates")
def list_templates():
    """Returns all template keys currently registered in the config."""
    return {"templates": list(_TEMPLATE_CONFIG.keys())}

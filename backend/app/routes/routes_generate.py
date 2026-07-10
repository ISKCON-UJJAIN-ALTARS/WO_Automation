import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config.template_config import load_template_config
from app.schemas.request_models import GenerateRequest, GenerateResponse
from app.services.sheets_service import write_inputs_and_read_outputs
from app.services.template_service import render_template

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Load resolved config once at import time ───────────────────────────────
# load_template_config() reads cell_groups.json + field_catalog.json +
# templates.json and reconstructs the same flat shape the rest of this file
# already expects (input_mappings/output_mappings/input_sheet/output_sheet),
# plus an extra "input_fields" list used below for per-template validation.
_TEMPLATE_CONFIG: dict = load_template_config()

# Base directory of the project (backend/)
_BASE_DIR = Path(__file__).resolve().parents[2]


@router.post("/generate", response_model=GenerateResponse, summary="Generate work-order image")
def generate_work_order(request: GenerateRequest):
    """
    Accepts altar/basebox dimensions, writes them into the sheet, reads
    calculated outputs, detects placeholders in the template image, replaces
    them with real values, and returns the path of the generated PNG.
    """
    template_key = request.template

    # ── Validate template key ─────────────────────────────────────────────
    if template_key not in _TEMPLATE_CONFIG:
        available = list(_TEMPLATE_CONFIG.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Template '{template_key}' not found. Available templates: {available}",
        )

    cfg = _TEMPLATE_CONFIG[template_key]

    # ── Validate required inputs for this specific template ───────────────
    # Different templates need different subsets of their group's fields
    # (e.g. 'back_side' only needs 3 basebox fields, 'bottom' needs 9), so
    # required-ness is checked per-template against cfg["input_fields"]
    # rather than via one rigid Pydantic model per group.
    provided = request.inputs.as_dict()
    required_keys = {f["key"] for f in cfg["input_fields"]}
    missing = required_keys - provided.keys()
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required inputs for '{template_key}': {sorted(missing)}",
        )

    # ── Step 1: Write inputs → read outputs via Sheets ─────────────────────
    logger.info("Processing template '%s' with inputs: %s", template_key, provided)

    try:
        output_values = write_inputs_and_read_outputs(
            inputs=provided,
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
        logger.exception("Unexpected error in sheets service")
        raise HTTPException(status_code=500, detail=f"Sheets processing error: {exc}")

    logger.info("Outputs: %s", output_values)

    # ── Step 2: Render template image ──────────────────────────────────────
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
    """Returns all templates with their image and input field metadata for form rendering."""
    return {
        name: {
            "template_image": cfg["template_image"],
            "input_fields": cfg["input_fields"],
        }
        for name, cfg in _TEMPLATE_CONFIG.items()
    }
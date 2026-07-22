import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.config.template_config import load_template_config
from app.schemas.request_models import GenerateRequest, GenerateResponse
from app.services.image_selector import resolve_image, resolve_output_mappings
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
    # (e.g. 'side_cutting' only needs 3 basebox fields, 'bottom' needs 9), so
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

    output_mappings = resolve_output_mappings(template_key, cfg, provided)

    try:
        output_values = write_inputs_and_read_outputs(
            inputs=provided,
            input_mappings=cfg["input_mappings"],
            output_mappings=output_mappings,
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
    # For most templates this is just the static template_image. For 'top'
    # and 'side_cutting' (which support more than one shape), image_rule tells
    # resolve_image() to pick the right variant based on the submitted
    # pillar_config / component_box / level_count values, falling back to
    # the default template_image if that exact combo has no artwork yet.
    template_abs_path = resolve_image(template_key, cfg, provided)

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


@router.get("/templates/{template_key}/preview-image", summary="Preview which shape image will be auto-selected")
def preview_template_image(template_key: str, request: Request):
    """
    Given the same shape-selector fields the wizard form collects (e.g.
    pillar_config, component_box, level_count as query params), returns the
    relative URL of the image that /generate would pick for this combo —
    without writing to Excel or rendering placeholders. Lets the frontend
    show a live preview as the user changes dropdowns.
    """
    if template_key not in _TEMPLATE_CONFIG:
        available = list(_TEMPLATE_CONFIG.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Template '{template_key}' not found. Available templates: {available}",
        )

    cfg = _TEMPLATE_CONFIG[template_key]
    provided = dict(request.query_params)

    image_path = resolve_image(template_key, cfg, provided)
    return {
        "template": template_key,
        "image_url": f"/template-assets/{image_path.name}",
        "is_fallback": image_path == (_BASE_DIR / cfg["template_image"]),
    }


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
            "image_rule": cfg.get("image_rule"),
        }
        for name, cfg in _TEMPLATE_CONFIG.items()
    }
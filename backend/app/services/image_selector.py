"""
Picks the correct shape-variant image for templates that have more than one
possible drawing (currently the basebox 'top' piece and the 'side_cutting'
piece), instead of always using one hardcoded template_image.

Two ways a combo can resolve to an image, tried in this order:

1. EXPLICIT LOOKUP TABLE (backend/app/config/image_variants.json)
   The authoritative source once a combo has been given to us on a rule
   chart. For 'top', rows are matched on:
     - component_box                    (used as-is, e.g. "top1_bottom3")
     - normalized pillar_config_front   (see _normalize_pillar_pattern)
     - normalized pillar_config_back
   Normalization: each of the 4 comma-separated positions in a pillar_config
   becomes '0' if it's exactly zero, otherwise 'x' — the actual pillar size
   (1 vs 2) doesn't change which image is used, only whether a pillar is
   present at that position. e.g. '1,0,0,1' and '2,0,0,2' both normalize to
   'x,0,0,x'.

2. NAMING-CONVENTION GUESS (fallback for combos not in the table yet)
     TOP  -> top_<front_code>_<back_code>_<component_box>.png
     SIDE -> side_step<N>_<component_box>.png, N = effective_steps(...)

If neither resolves to a file that actually exists on disk, we fall back to
the template's default `template_image` and log a warning — so missing
artwork never breaks generation, it just quietly uses a placeholder until
the real file (or table row) is added.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parents[2]  # backend/
_TEMPLATES_DIR = _BASE_DIR / "templates"
_IMAGE_VARIANTS_PATH = _BASE_DIR / "app" / "config" / "image_variants.json"


def _load_image_variants() -> Dict[str, List[Dict[str, str]]]:
    try:
        with open(_IMAGE_VARIANTS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    data.pop("_comment", None)
    return data


_IMAGE_VARIANTS = _load_image_variants()


def _normalize_pillar_pattern(value: Any) -> str:
    """'1,0,0,1' -> 'x,0,0,x'   '2,2,2,2' -> 'x,x,x,x'   '1,2,2,1' -> 'x,x,x,x'"""
    parts = [p.strip() for p in str(value).split(",")]
    return ",".join("0" if p == "0" else "x" for p in parts)


def _pillar_code(value: Any) -> str:
    """'1,x,x,1' -> '1xx1'   '2,0,0,2' -> '2002'  (used only by the fallback guess)"""
    return "".join(part.strip() for part in str(value).split(","))


def effective_steps(level_count: Any, component_box: Any) -> int:
    """How many visible steps the side-cutting drawing needs."""
    box_present = component_box not in (None, "none", "", "None")
    steps = int(level_count) - 1 - (1 if box_present else 0)
    return max(steps, 0)


def _lookup_top_table(provided: Dict[str, Any], fields: list) -> Optional[Path]:
    rows = _IMAGE_VARIANTS.get("top")
    if not rows:
        return None
    front_field, back_field, box_field = (fields + [None, None, None])[:3]
    front = provided.get(front_field) if front_field else None
    back = provided.get(back_field) if back_field else None
    if front is None or back is None:
        return None
    component_box = (provided.get(box_field) if box_field else None) or "none"

    front_pattern = _normalize_pillar_pattern(front)
    back_pattern = _normalize_pillar_pattern(back)

    for row in rows:
        if (
            row.get("component_box") == component_box
            and row.get("pillar_front_pattern") == front_pattern
            and row.get("pillar_back_pattern") == back_pattern
        ):
            return _TEMPLATES_DIR / row["image"]
    return None


def _lookup_side_table(provided: Dict[str, Any], fields: list) -> Optional[Path]:
    rows = _IMAGE_VARIANTS.get("side_cutting")
    if not rows:
        return None
    level_field, box_field = (fields + [None, None])[:2]
    level_count = provided.get(level_field) if level_field else None
    if level_count is None:
        return None
    component_box = (provided.get(box_field) if box_field else None) or "none"

    try:
        level_count = int(level_count)
    except (TypeError, ValueError):
        return None

    for row in rows:
        if row.get("component_box") == component_box and int(row.get("level_count", -1)) == level_count:
            return _TEMPLATES_DIR / row["image"]
    return None


def _lookup_level_table(template_key: str, provided: Dict[str, Any], fields: list) -> Optional[Path]:
    rows = _IMAGE_VARIANTS.get(template_key)
    if not rows:
        return None
    level_field = fields[0] if fields else None
    level_count = provided.get(level_field) if level_field else None
    if level_count is None:
        return None
    try:
        level_count = int(level_count)
    except (TypeError, ValueError):
        return None

    for row in rows:
        if int(row.get("level_count", -1)) == level_count:
            return _TEMPLATES_DIR / row["image"]
    return None
    """Naming-convention fallback guess, used only if the table has no matching row."""
    front_field, back_field, box_field = (fields + [None, None, None])[:3]
    front = provided.get(front_field) if front_field else None
    back = provided.get(back_field) if back_field else None
    if front is None or back is None:
        return None
    component_box = (provided.get(box_field) if box_field else None) or "none"
    filename = f"{prefix}_{_pillar_code(front)}_{_pillar_code(back)}_{component_box}.png"
    return _TEMPLATES_DIR / filename


def _find_side_image(provided: Dict[str, Any], prefix: str, fields: list) -> Optional[Path]:
    level_field, box_field = (fields + [None, None])[:2]
    level_count = provided.get(level_field) if level_field else None
    if level_count is None:
        return None
    component_box = (provided.get(box_field) if box_field else None) or "none"
    steps = effective_steps(level_count, component_box)
    return _TEMPLATES_DIR / f"{prefix}_step{steps}_{component_box}.png"


def resolve_image(template_key: str, cfg: Dict[str, Any], provided: Dict[str, Any]) -> Path:
    """Returns the absolute path of the image to render for this request."""
    default_path = _BASE_DIR / cfg["template_image"]
    rule = cfg.get("image_rule")
    if not rule:
        return default_path

    rule_type = rule.get("type")
    prefix = rule.get("prefix", template_key)
    fields = rule.get("fields", [])

    candidate: Optional[Path] = None
    if rule_type == "pillar_and_box":
        candidate = _lookup_top_table(provided, fields)
        if not (candidate and candidate.exists()):
            candidate = _find_top_image(provided, prefix, fields)
    elif rule_type == "steps_and_box":
        candidate = _lookup_side_table(provided, fields)
        if not (candidate and candidate.exists()):
            candidate = _find_side_image(provided, prefix, fields)
    elif rule_type == "level_steps":
        candidate = _lookup_level_table(template_key, provided, fields)

    if candidate and candidate.exists():
        return candidate

    logger.warning(
        "No shape-variant image found for template '%s' (rule=%s, looked for %s) — "
        "falling back to default image '%s'.",
        template_key, rule_type, candidate, default_path,
    )
    return default_path

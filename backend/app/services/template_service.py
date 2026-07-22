import logging
import time
from pathlib import Path
from typing import Dict, Any, Tuple

import cv2
import numpy as np

from app.services.ocr_service import detect_placeholders, PlaceholderMatch

logger = logging.getLogger(__name__)

# Directory where generated images are saved (relative to repo root)
_GENERATED_DIR = Path(__file__).resolve().parents[2] / "generated"
_GENERATED_DIR.mkdir(parents=True, exist_ok=True)

# ── Font settings ─────────────────────────────────────────────────────────────
_FONT       = cv2.FONT_HERSHEY_SIMPLEX
_FONT_SCALE = 2
_FONT_THICK = 2
# No hardcoded _TEXT_COLOR anymore — each placeholder's replacement text is
# rendered in that same placeholder's own original color (match.color),
# sampled during OCR detection, so e.g. a green {H} label's replacement
# value is also drawn in that same green rather than always black.


def _sample_background_color(
    image: np.ndarray,
    x: int,
    y: int,
    w: int,
    h: int,
    border: int = 4,
) -> Tuple[int, int, int]:
    """
    Sample the median color of a thin border *around* the bounding box
    to use as the cover colour.  Falls back to white if sampling fails.
    """
    H, W = image.shape[:2]
    rows, cols = [], []

    # top / bottom strips
    for dy in range(-border, 0):
        for dx in range(w):
            rr, cc = y + dy, x + dx
            if 0 <= rr < H and 0 <= cc < W:
                rows.append(rr); cols.append(cc)
    for dy in range(h, h + border):
        for dx in range(w):
            rr, cc = y + dy, x + dx
            if 0 <= rr < H and 0 <= cc < W:
                rows.append(rr); cols.append(cc)

    # left / right strips
    for dy in range(h):
        for ddx in range(-border, 0):
            rr, cc = y + dy, x + ddx
            if 0 <= rr < H and 0 <= cc < W:
                rows.append(rr); cols.append(cc)
        for ddx in range(w, w + border):
            rr, cc = y + dy, x + ddx
            if 0 <= rr < H and 0 <= cc < W:
                rows.append(rr); cols.append(cc)

    if not rows:
        return (255, 255, 255)

    pixels = image[rows, cols]          # shape (N, 3)
    median = np.median(pixels, axis=0).astype(int)
    return (int(median[0]), int(median[1]), int(median[2]))


def _cover_and_write(
    image: np.ndarray,
    match: PlaceholderMatch,
    display_text: str,
) -> None:
    """
    1. Cover the placeholder bounding box with the surrounding background colour.
    2. Draw *display_text* centred inside the same box, in that same
       placeholder's own original color (match.color).

    Mutates *image* in-place.
    """
    x, y, w, h = match.x, match.y, match.w, match.h

    bg_color = _sample_background_color(image, x, y, w, h)
    cv2.rectangle(image, (x, y), (x + w, y + h), bg_color, thickness=-1)

    # Centre the text
    (tw, th), baseline = cv2.getTextSize(display_text, _FONT, _FONT_SCALE, _FONT_THICK)
    cx = x + w // 2
    ty = y + (h + th) // 2

    tx = cx - tw // 2
    
    cv2.putText(
        image,
        display_text,
        (tx, ty),
        _FONT,
        _FONT_SCALE,
        match.color,
        _FONT_THICK,
        lineType=cv2.LINE_AA,
    )
    logger.debug(
        "Replaced %s with '%s' at (%d,%d) in color(BGR)=%s", match.token, display_text, x, y, match.color
    )


def render_template(template_path: str | Path, values: Dict[str, Any]) -> Path:
   
    template_path = Path(template_path)
    if not template_path.exists():
        raise FileNotFoundError(f"Template image not found: {template_path}")

    logger.info("Rendering template: %s", template_path)

    image = cv2.imread(str(template_path))
    if image is None:
        raise ValueError(f"OpenCV could not decode image: {template_path}")

    placeholders = detect_placeholders(image)

    if not placeholders:
        logger.warning("No placeholders detected in %s – image returned unchanged.", template_path)
    else:
        for match in placeholders:
            if match.key in values:
                raw_val = values[match.key]
                # Format floats neatly; keep int / str as-is
                if isinstance(raw_val, float):
                    display = f"{raw_val:.4g}"
                else:
                    display = str(raw_val) if raw_val is not None else ""
                _cover_and_write(image, match, display)
            else:
                logger.warning(
                    "Placeholder %s found in image but no value provided – skipping.", match.token
                )

    timestamp = int(time.time() * 1000)
    stem = template_path.stem
    output_filename = f"{stem}_{timestamp}.png"
    output_path = _GENERATED_DIR / output_filename

    cv2.imwrite(str(output_path), image)
    logger.info("Generated image saved to: %s", output_path)

    return output_path
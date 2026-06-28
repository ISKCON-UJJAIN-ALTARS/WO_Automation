import logging
import re
from dataclasses import dataclass
from typing import List

import cv2
import numpy as np
import pytesseract
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r"D:\New folder\tesseract.exe"
logger = logging.getLogger(__name__)

# Regex that matches tokens like {TL}, {TSH}, {OW} …
_PLACEHOLDER_RE = re.compile(r"\{[A-Z][A-Z0-9_]*\}")


@dataclass
class PlaceholderMatch:
    token: str          # e.g. "{TL}"
    key: str            # e.g. "TL"
    x: int
    y: int
    w: int
    h: int


def _isolate_label_text(image: np.ndarray) -> np.ndarray:
    """
    Strip out everything except the red placeholder-label text, replacing it
    with pure black-on-white. This is necessary because the cyan/orange
    dimension-line art in these drawings sits close enough to some labels
    (e.g. the second {TL} next to the {VH} dimension line) that Tesseract's
    text segmentation merges the line art and the glyphs into a single
    unreadable blob, silently dropping that placeholder from detection.

    Placeholder labels in these templates are consistently rendered in a
    saturated red (BGR roughly (49, 49, 255)), distinct from the cyan/orange
    dimension lines and the black outline. Isolating by color is far more
    robust than trying to tune OCR page-segmentation parameters, and keeps
    the "no hardcoded coordinates" design intact since it works on any
    template that follows the same red-label convention.

    Args:
        image: BGR numpy array (as returned by cv2.imread)

    Returns:
        A new BGR image, white background, with only the red text rendered
        as solid black. The original image passed in is not modified —
        rendering still happens against the original color image.
    """
    b, g, r = cv2.split(image)
    # A pixel counts as "label text" if the red channel clearly dominates
    # over both blue and green — this isolates red glyphs from cyan
    # (high blue+green) and black/gray outline (all channels roughly equal).
    red_mask = (r.astype(int) - cv2.max(b, g).astype(int)) > 40

    isolated = np.full_like(image, 255)
    isolated[red_mask] = (0, 0, 0)
    return isolated


def detect_placeholders(image: np.ndarray) -> List[PlaceholderMatch]:
    """
    Run Tesseract on *image* and return every placeholder token found
    together with its bounding box.

    Args:
        image: BGR numpy array (as returned by cv2.imread)

    Returns:
        List of PlaceholderMatch objects; may be empty if none detected.
    """
    # Isolate the red label text before handing the image to Tesseract, so
    # nearby dimension-line art can't get merged into the same OCR "word".
    # The original `image` argument is untouched — only this OCR-input copy
    # is transformed.
    ocr_input = _isolate_label_text(image)
    rgb = cv2.cvtColor(ocr_input, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)

    try:
        data = pytesseract.image_to_data(
            pil_img,
            output_type=pytesseract.Output.DICT,
            config="--psm 11",   # sparse text – finds characters anywhere
        )
    except pytesseract.TesseractNotFoundError:
        logger.error(
            "Tesseract not found. Install it and ensure 'tesseract' is on PATH."
        )
        raise

    n = len(data["text"])
    matches: List[PlaceholderMatch] = []

    for i in range(n):
        word = (data["text"][i] or "").strip()
        if not word:
            continue

        # Log every raw OCR word at DEBUG level to help diagnose misreads
        logger.debug("OCR raw word: '%s'", word)

        found = _PLACEHOLDER_RE.findall(word)
        for token in found:
            key = token[1:-1]   # strip braces
            x = int(data["left"][i])
            y = int(data["top"][i])
            w = int(data["width"][i])
            h = int(data["height"][i])
            logger.debug("Detected placeholder %s at (%d,%d) size %dx%d", token, x, y, w, h)
            matches.append(PlaceholderMatch(token=token, key=key, x=x, y=y, w=w, h=h))

    logger.info("OCR found %d placeholder(s) in image.", len(matches))
    return matches
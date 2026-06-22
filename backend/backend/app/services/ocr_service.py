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


def detect_placeholders(image: np.ndarray) -> List[PlaceholderMatch]:
    """
    Run Tesseract on *image* and return every placeholder token found
    together with its bounding box.

    Args:
        image: BGR numpy array (as returned by cv2.imread)

    Returns:
        List of PlaceholderMatch objects; may be empty if none detected.
    """
    # Convert to RGB for Pillow / tesseract
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
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

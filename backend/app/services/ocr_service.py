import logging
import os
import re
import shutil
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)

_TESSERACT_CMD = (
    os.environ.get("TESSERACT_CMD")
    or shutil.which("tesseract")
    or r"D:\New folder\tesseract.exe"
)
pytesseract.pytesseract.tesseract_cmd = _TESSERACT_CMD
logger.info("Using Tesseract binary at: %s", _TESSERACT_CMD)


_PLACEHOLDER_RE = re.compile(r"\{([A-Z0-9_]+)\}")
_CHAR_WHITELIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789{}_"

_SAT_THRESHOLD = 50
_VAL_MIN = 30

_OPEN_KERNEL_SIZE = 2
_MIN_COMPONENT_AREA = 2
_MAX_COMPONENT_FRACTION = 0.15
_MAX_CLUSTER_ASPECT_RATIO = 20.0

# Upscale factor applied to each isolated placeholder crop before OCR.
_OCR_SCALE = 3

# Two components are considered part of the SAME placeholder token only if
# they are close together AND similar in color. This is what keeps
# neighbouring-but-different labels (e.g. a green {H3} next to a purple
# {L3}) from being fused into one OCR read.
_COLOR_DIST_THRESHOLD = 55.0   # Euclidean distance in BGR space
_GAP_HEIGHT_MULTIPLIER = 1.6   # max horizontal gap, in units of avg comp height
_VERTICAL_ALIGN_FRACTION = 0.8  # max centroid y-difference, in units of avg comp height

_CANVAS_PAD = 4

# --- NEW: arrow / icon rejection ---
# Diagrams draw double-headed arrows (<->  or  updown) and solid little box
# icons in the SAME color as the nearby {KEY} text. Since clustering only
# looks at color + proximity, those non-text shapes were getting unioned
# into the placeholder's cluster and corrupting the OCR crop (extra strokes
# / a filled square where a letter should be). We reject them up front,
# before they ever enter `_cluster_components`, using simple shape stats:
#   - arrows: long & thin, mostly empty inside their bbox (low "extent")
#   - box icons: near-square AND almost completely filled (high "extent")
# Real glyphs sit between these two profiles, so genuine {KEY} letters are
# left untouched.
_ARROW_ASPECT_MIN = 4.0      # long, thin double-headed line
_ARROW_EXTENT_MAX = 0.30     # very low fill (mostly empty bbox, thin stroke)

_ICON_EXTENT_MIN = 0.78      # solid box icons are almost fully filled
_ICON_ASPECT_MIN = 0.6       # roughly square...
_ICON_ASPECT_MAX = 1.6       # ...unlike most letters
_ICON_MIN_SIZE = 18          # and bigger than a single glyph stroke


def _is_arrow_or_icon(w: int, h: int, area: int) -> bool:
    """Return True if a component's shape stats look like a directional
    arrow (<->/^v) or a solid box icon rather than a text glyph, so it can
    be excluded before clustering ever sees it."""
    if w <= 0 or h <= 0:
        return False
    aspect = max(w, h) / max(min(w, h), 1)
    extent = area / float(w * h)

    # Thin elongated stroke -> arrow
    if aspect >= _ARROW_ASPECT_MIN and extent <= _ARROW_EXTENT_MAX:
        return True

    # Near-square, almost fully solid, and larger than a glyph -> box icon
    if (_ICON_ASPECT_MIN <= (w / max(h, 1)) <= _ICON_ASPECT_MAX
            and extent >= _ICON_EXTENT_MIN
            and min(w, h) >= _ICON_MIN_SIZE):
        return True

    return False


@dataclass
class PlaceholderMatch:
    token: str
    key: str
    x: int       # coordinates in the ORIGINAL (unscaled) image
    y: int
    w: int
    h: int
    color: Tuple[int, int, int]


def _colored_mask(image: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    return (s > _SAT_THRESHOLD) & (v > _VAL_MIN)


def _connected_components(image: np.ndarray) -> Tuple[np.ndarray, np.ndarray, List[dict]]:
    """Find individual glyph-ish blobs, filter noise, and report each kept
    component's own bbox + color. Returns (labels, keep_mask, components)."""
    mask = _colored_mask(image).astype(np.uint8) * 255
    kernel = np.ones((_OPEN_KERNEL_SIZE, _OPEN_KERNEL_SIZE), np.uint8)
    opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(opened, connectivity=8)
    img_h, img_w = mask.shape[:2]

    keep_ids: List[int] = []
    rejected_shapes = 0
    for label_id in range(1, num_labels):
        x, y, w, h, area = stats[label_id]
        if area < _MIN_COMPONENT_AREA:
            continue
        if w > _MAX_COMPONENT_FRACTION * img_w or h > _MAX_COMPONENT_FRACTION * img_h:
            continue
        if _is_arrow_or_icon(w, h, area):
            rejected_shapes += 1
            continue
        keep_ids.append(label_id)

    if rejected_shapes:
        logger.debug("Rejected %d component(s) as arrow/icon shapes before clustering.", rejected_shapes)

    keep_mask = np.isin(labels, keep_ids) if keep_ids else np.zeros(mask.shape, dtype=bool)

    components: List[dict] = []
    for label_id in keep_ids:
        x, y, w, h, area = stats[label_id]
        comp_mask = labels == label_id
        pixels = image[comp_mask]
        color = tuple(int(v) for v in np.median(pixels.reshape(-1, 3), axis=0)) if pixels.size else (0, 0, 0)
        components.append({
            "label_id": label_id, "x": int(x), "y": int(y),
            "w": int(w), "h": int(h), "area": int(area), "color": color,
        })

    return labels, keep_mask, components


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def _cluster_components(components: List[dict]) -> List[List[dict]]:
    """Group components into probable single-placeholder clusters using
    spatial proximity + color similarity, so that visually distinct
    placeholders never get merged even if they sit close together."""
    n = len(components)
    uf = _UnionFind(n)
    for i in range(n):
        a = components[i]
        for j in range(i + 1, n):
            b = components[j]
            avg_h = (a["h"] + b["h"]) / 2.0
            if avg_h <= 0:
                continue

            a_cy = a["y"] + a["h"] / 2.0
            b_cy = b["y"] + b["h"] / 2.0
            if abs(a_cy - b_cy) > avg_h * _VERTICAL_ALIGN_FRACTION:
                continue

            if a["x"] <= b["x"]:
                gap = b["x"] - (a["x"] + a["w"])
            else:
                gap = a["x"] - (b["x"] + b["w"])
            if gap > avg_h * _GAP_HEIGHT_MULTIPLIER:
                continue

            ca, cb = np.array(a["color"], dtype=float), np.array(b["color"], dtype=float)
            if np.linalg.norm(ca - cb) > _COLOR_DIST_THRESHOLD:
                continue

            uf.union(i, j)

    groups: Dict[int, List[dict]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(components[i])
    return list(groups.values())


def _cluster_bbox(cluster: List[dict]) -> Tuple[int, int, int, int]:
    xs = [c["x"] for c in cluster]
    ys = [c["y"] for c in cluster]
    x2s = [c["x"] + c["w"] for c in cluster]
    y2s = [c["y"] + c["h"] for c in cluster]
    x0, y0 = min(xs), min(ys)
    return x0, y0, max(x2s) - x0, max(y2s) - y0


def _cluster_color(cluster: List[dict]) -> Tuple[int, int, int]:
    colors = np.array([c["color"] for c in cluster], dtype=float)
    median = np.median(colors, axis=0).astype(int)
    return tuple(int(v) for v in median)


def _render_cluster_canvas(
    labels: np.ndarray, cluster: List[dict], pad: int = _CANVAS_PAD
) -> Tuple[Image.Image, int, int]:
    """Paint ONLY this cluster's own pixels black on an isolated white
    canvas, so OCR can never see a neighbouring placeholder's glyphs."""
    H, W = labels.shape[:2]
    x0, y0, w, h = _cluster_bbox(cluster)
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(W, x0 + w + 2 * pad)
    y1 = min(H, y0 + h + 2 * pad)

    crop_labels = labels[y0:y1, x0:x1]
    label_ids = {c["label_id"] for c in cluster}
    cluster_mask = np.isin(crop_labels, list(label_ids))

    canvas = np.full((y1 - y0, x1 - x0, 3), 255, dtype=np.uint8)
    canvas[cluster_mask] = (0, 0, 0)

    scale = _OCR_SCALE
    scaled = cv2.resize(
        canvas, (canvas.shape[1] * scale, canvas.shape[0] * scale),
        interpolation=cv2.INTER_CUBIC,
    )
    pil_img = Image.fromarray(cv2.cvtColor(scaled, cv2.COLOR_BGR2RGB))
    return pil_img, x0, y0


def _ocr_single_token(pil_img: Image.Image) -> str:
    text = pytesseract.image_to_string(
        pil_img, config=f"--psm 7 -c tessedit_char_whitelist={_CHAR_WHITELIST}"
    )
    return text.strip()


def _char_boxes_for_crop(pil_crop: Image.Image) -> List[Tuple[str, int, int, int, int]]:
    img_w, img_h = pil_crop.size
    boxes_str = pytesseract.image_to_boxes(
        pil_crop, config=f"--psm 7 -c tessedit_char_whitelist={_CHAR_WHITELIST}"
    )
    entries: List[Tuple[str, int, int, int, int]] = []
    for line in boxes_str.strip().splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        ch = parts[0]
        left, bottom, right, top = (int(p) for p in parts[1:5])
        x = left
        y = img_h - top
        w = right - left
        h = top - bottom
        entries.append((ch, x, y, w, h))
    entries.sort(key=lambda e: e[1])
    return entries


def _split_cluster_into_tokens(
    pil_img: Image.Image, x0: int, y0: int, scale: int
) -> List[Tuple[str, int, int, int, int]]:
    """Rare fallback: a single color+proximity cluster still contains more
    than one {KEY} (e.g. two same-colored tokens sitting close together).
    Use per-character boxes, restricted to this already-isolated canvas, to
    split it safely."""
    entries = _char_boxes_for_crop(pil_img)
    if not entries:
        return []
    concat = "".join(e[0] for e in entries)
    results: List[Tuple[str, int, int, int, int]] = []
    for m in _PLACEHOLDER_RE.finditer(concat):
        span = entries[m.start(): m.end()]
        if not span:
            continue
        xs = [e[1] for e in span]
        ys = [e[2] for e in span]
        x2s = [e[1] + e[3] for e in span]
        y2s = [e[2] + e[4] for e in span]
        bx, by = min(xs), min(ys)
        bw, bh = max(x2s) - bx, max(y2s) - by
        # unscale back to original image coordinates
        results.append((
            m.group(1),
            x0 + bx // scale, y0 + by // scale,
            bw // scale, bh // scale,
        ))
    return results


def _filter_clusters(clusters: List[List[dict]], img_shape: Tuple[int, int]) -> List[List[dict]]:
    img_h, img_w = img_shape[:2]
    kept: List[List[dict]] = []
    for cluster in clusters:
        _, _, w, h = _cluster_bbox(cluster)
        if w > _MAX_COMPONENT_FRACTION * img_w or h > _MAX_COMPONENT_FRACTION * img_h:
            continue
        aspect = max(w, h) / max(min(w, h), 1)
        if len(cluster) == 1 and aspect > _MAX_CLUSTER_ASPECT_RATIO:
            continue
        kept.append(cluster)
    return kept


def detect_placeholders(
    image: np.ndarray, known_keys: Optional[set] = None
) -> List[PlaceholderMatch]:
    """known_keys, when given, is the set of output keys this render actually
    expects (e.g. the keys of the values dict passed to render_template()).
    Some template PNGs have inconsistently-authored placeholders — most are
    drawn as '{KEY}' but a few are just a bare 'KEY' with no braces at all
    (verified by inspecting the source pixels, not an OCR artifact). When the
    normal '{KEY}' regex finds nothing, a bare OCR read that exactly matches
    one of known_keys is still accepted, so those assets don't silently fail."""
    labels, keep_mask, components = _connected_components(image)

    debug_mask = np.full_like(image, 255)
    debug_mask[keep_mask] = (0, 0, 0)
    cv2.imwrite("generated/ocr_debug.png", debug_mask)

    clusters = _cluster_components(components)
    clusters = _filter_clusters(clusters, image.shape)
    logger.info("Formed %d candidate placeholder cluster(s) from %d component(s).",
                len(clusters), len(components))

    matches: List[PlaceholderMatch] = []

    for cluster in clusters:
        pil_img, x0, y0 = _render_cluster_canvas(labels, cluster)
        raw_text = _ocr_single_token(pil_img)
        found = list(_PLACEHOLDER_RE.finditer(raw_text))

        cx, cy, cw, ch = _cluster_bbox(cluster)
        color = _cluster_color(cluster)

        if len(found) == 1:
            key = found[0].group(1)
            token = "{" + key + "}"
            matches.append(PlaceholderMatch(token=token, key=key, x=cx, y=cy, w=cw, h=ch, color=color))
            logger.debug("Cluster at (%d,%d) -> %s (raw ocr='%s')", cx, cy, token, raw_text)

        elif len(found) > 1:
            logger.warning(
                "Cluster at (%d,%d) OCR'd as '%s' — contains multiple placeholders, splitting.",
                cx, cy, raw_text,
            )
            split = _split_cluster_into_tokens(pil_img, x0, y0, _OCR_SCALE)
            if split:
                for key, sx, sy, sw, sh in split:
                    token = "{" + key + "}"
                    matches.append(PlaceholderMatch(token=token, key=key, x=sx, y=sy, w=sw, h=sh, color=color))
                    logger.debug("Split cluster -> %s at (%d,%d)", token, sx, sy)
            else:
                logger.warning("Could not split cluster '%s'; keeping merged tokens as-is.", raw_text)
                for m in found:
                    key = m.group(1)
                    token = "{" + key + "}"
                    matches.append(PlaceholderMatch(token=token, key=key, x=cx, y=cy, w=cw, h=ch, color=color))

        else:
            # No valid {KEY} read on first pass — retry once with a looser
            # single-word mode before giving up, small crops sometimes need it.
            fallback_text = pytesseract.image_to_string(
                pil_img, config=f"--psm 8 -c tessedit_char_whitelist={_CHAR_WHITELIST}"
            ).strip()
            fallback_found = list(_PLACEHOLDER_RE.finditer(fallback_text))
            if len(fallback_found) == 1:
                key = fallback_found[0].group(1)
                token = "{" + key + "}"
                matches.append(PlaceholderMatch(token=token, key=key, x=cx, y=cy, w=cw, h=ch, color=color))
                logger.debug("Cluster at (%d,%d) -> %s (psm8 fallback, raw ocr='%s')", cx, cy, token, fallback_text)
            else:
                bare_match = None
                if known_keys:
                    for raw in (raw_text, fallback_text):
                        candidate = raw.strip("{} ").upper()
                        if candidate in known_keys:
                            bare_match = candidate
                            break
                if bare_match:
                    token = "{" + bare_match + "}"
                    matches.append(PlaceholderMatch(token=token, key=bare_match, x=cx, y=cy, w=cw, h=ch, color=color))
                    logger.debug(
                        "Cluster at (%d,%d) -> %s (bare key match, no braces in source image, raw ocr='%s')",
                        cx, cy, token, raw_text,
                    )
                else:
                    logger.warning(
                        "Cluster at (%d,%d) size %dx%d produced no placeholder match "
                        "(psm7='%s', psm8='%s') — skipping.",
                        cx, cy, cw, ch, raw_text, fallback_text,
                    )

    logger.info("OCR found %d placeholder(s) in image.", len(matches))
    return matches
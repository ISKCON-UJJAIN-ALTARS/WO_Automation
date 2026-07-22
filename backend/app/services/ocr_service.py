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
# Bumped from 3 -> 5: small/thin single-character clusters (e.g. "{S}")
# were reading as empty strings or noise ('EE', 'CE') at 3x.
_OCR_SCALE = 5

# Two components are considered part of the SAME placeholder token only if
# they are close together AND similar in color. This is what keeps
# neighbouring-but-different labels (e.g. a green {H3} next to a purple
# {L3}) from being fused into one OCR read.
_COLOR_DIST_THRESHOLD = 55.0   # Euclidean distance in BGR space
_GAP_HEIGHT_MULTIPLIER = 1.6   # max horizontal gap, in units of ref comp height
_VERTICAL_ALIGN_FRACTION = 0.4  # max centroid y-difference, in units of ref comp height
# NOTE: previously 0.8, and computed against the AVERAGE of the two
# components' heights. That let a single anomalously-tall component (e.g.
# antialiasing bridging two glyphs) drag its threshold up and wrongly merge
# components sitting on different rows into one giant cluster. We now use
# min(h) as the reference height (see _cluster_components) and tightened
# the fraction, both of which make row-bridging much harder.

# When the first-pass cluster is retried at a stricter alignment tolerance
# (row-aware re-split), use this much tighter fraction.
_RESPLIT_VERTICAL_ALIGN_FRACTION = 0.15
_RESPLIT_GAP_HEIGHT_MULTIPLIER = 1.2

_CANVAS_PAD = 4

_DEBUG_DIR = "generated/ocr_debug_clusters"


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
    for label_id in range(1, num_labels):
        x, y, w, h, area = stats[label_id]
        if area < _MIN_COMPONENT_AREA:
            continue
        if w > _MAX_COMPONENT_FRACTION * img_w or h > _MAX_COMPONENT_FRACTION * img_h:
            continue
        keep_ids.append(label_id)

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


def _cluster_components(
    components: List[dict],
    vertical_align_fraction: float = _VERTICAL_ALIGN_FRACTION,
    gap_height_multiplier: float = _GAP_HEIGHT_MULTIPLIER,
) -> List[List[dict]]:
    """Group components into probable single-placeholder clusters using
    spatial proximity + color similarity, so that visually distinct
    placeholders never get merged even if they sit close together.

    Reference height for both the gap and vertical-alignment checks is
    min(a.h, b.h) rather than the average: this stops one abnormally tall
    component (e.g. antialiasing bridging two glyphs, or a stray bracket)
    from inflating the tolerance and pulling in a component from a
    different row/placeholder.
    """
    n = len(components)
    uf = _UnionFind(n)
    for i in range(n):
        a = components[i]
        for j in range(i + 1, n):
            b = components[j]
            ref_h = min(a["h"], b["h"])
            if ref_h <= 0:
                continue

            a_cy = a["y"] + a["h"] / 2.0
            b_cy = b["y"] + b["h"] / 2.0
            if abs(a_cy - b_cy) > ref_h * vertical_align_fraction:
                continue

            if a["x"] <= b["x"]:
                gap = b["x"] - (a["x"] + a["w"])
            else:
                gap = a["x"] - (b["x"] + b["w"])
            if gap > ref_h * gap_height_multiplier:
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


def _dump_debug_canvas(pil_img: Image.Image, idx: int, x0: int, y0: int, tag: str = "") -> None:
    try:
        os.makedirs(_DEBUG_DIR, exist_ok=True)
        suffix = f"_{tag}" if tag else ""
        path = os.path.join(_DEBUG_DIR, f"cluster_{idx:02d}_{x0}_{y0}{suffix}.png")
        pil_img.save(path)
    except Exception:
        logger.exception("Failed to write debug cluster canvas (idx=%d)", idx)


def _ocr_single_token(pil_img: Image.Image, psm: int) -> str:
    text = pytesseract.image_to_string(
        pil_img, config=f"--psm {psm} -c tessedit_char_whitelist={_CHAR_WHITELIST}"
    )
    return text.strip()


def _ocr_with_fallbacks(pil_img: Image.Image) -> Tuple[str, int]:
    """Try a sequence of PSM modes until one yields exactly one clean
    {KEY} match. Returns (text, psm_used)."""
    for psm in (7, 8, 6):
        text = _ocr_single_token(pil_img, psm)
        if len(list(_PLACEHOLDER_RE.finditer(text))) >= 1:
            return text, psm
    # nothing matched cleanly on any pass; return the psm7 read for logging
    return _ocr_single_token(pil_img, 7), 7


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
    """Fallback: a single color+proximity cluster still contains more than
    one {KEY} (e.g. two same-colored tokens sitting close together, or two
    rows that survived the row re-split). Use per-character boxes,
    restricted to this already-isolated canvas, to split it safely."""
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


def _resplit_cluster_by_rows(cluster: List[dict]) -> List[List[dict]]:
    """Re-cluster a single (probably over-merged) cluster's own components
    using a much stricter vertical-alignment tolerance. This recovers
    cases where the original pass fused two different rows/placeholders
    into one oversized bbox that then OCR'd as garbage (e.g. '{A', '}',
    'W}1N}'). If the stricter pass still yields just one group, there was
    nothing to split and the caller should fall back to character-box
    splitting instead."""
    if len(cluster) < 2:
        return [cluster]
    subclusters = _cluster_components(
        cluster,
        vertical_align_fraction=_RESPLIT_VERTICAL_ALIGN_FRACTION,
        gap_height_multiplier=_RESPLIT_GAP_HEIGHT_MULTIPLIER,
    )
    return subclusters


def _ocr_cluster(
    labels: np.ndarray, cluster: List[dict], idx: int, log_prefix: str = ""
) -> List[PlaceholderMatch]:
    """Run the full OCR pipeline (render -> OCR w/ fallbacks -> split if
    needed) against a single cluster and return whatever matches it
    resolves to. Used both for the initial pass and for row-resplit
    subclusters."""
    pil_img, x0, y0 = _render_cluster_canvas(labels, cluster)
    _dump_debug_canvas(pil_img, idx, x0, y0, tag=log_prefix)

    raw_text, psm_used = _ocr_with_fallbacks(pil_img)
    found = list(_PLACEHOLDER_RE.finditer(raw_text))

    cx, cy, cw, ch = _cluster_bbox(cluster)
    color = _cluster_color(cluster)

    matches: List[PlaceholderMatch] = []

    if len(found) == 1:
        key = found[0].group(1)
        token = "{" + key + "}"
        matches.append(PlaceholderMatch(token=token, key=key, x=cx, y=cy, w=cw, h=ch, color=color))
        logger.debug(
            "%sCluster at (%d,%d) -> %s (psm%d ocr='%s')",
            log_prefix, cx, cy, token, psm_used, raw_text,
        )
        return matches

    if len(found) > 1:
        logger.warning(
            "%sCluster at (%d,%d) OCR'd as '%s' — contains multiple placeholders, splitting.",
            log_prefix, cx, cy, raw_text,
        )
        split = _split_cluster_into_tokens(pil_img, x0, y0, _OCR_SCALE)
        if split:
            for key, sx, sy, sw, sh in split:
                token = "{" + key + "}"
                matches.append(PlaceholderMatch(token=token, key=key, x=sx, y=sy, w=sw, h=sh, color=color))
                logger.debug("%sSplit cluster -> %s at (%d,%d)", log_prefix, token, sx, sy)
        else:
            logger.warning("%sCould not split cluster '%s'; keeping merged tokens as-is.", log_prefix, raw_text)
            for m in found:
                key = m.group(1)
                token = "{" + key + "}"
                matches.append(PlaceholderMatch(token=token, key=key, x=cx, y=cy, w=cw, h=ch, color=color))
        return matches

    return matches  # empty: caller decides what to try next


def detect_placeholders(image: np.ndarray) -> List[PlaceholderMatch]:
    labels, keep_mask, components = _connected_components(image)

    debug_mask = np.full_like(image, 255)
    debug_mask[keep_mask] = (0, 0, 0)
    os.makedirs("generated", exist_ok=True)
    cv2.imwrite("generated/ocr_debug.png", debug_mask)

    clusters = _cluster_components(components)
    clusters = _filter_clusters(clusters, image.shape)
    logger.info("Formed %d candidate placeholder cluster(s) from %d component(s).",
                len(clusters), len(components))

    matches: List[PlaceholderMatch] = []

    for idx, cluster in enumerate(clusters):
        cluster_matches = _ocr_cluster(labels, cluster, idx)

        if cluster_matches:
            matches.extend(cluster_matches)
            continue

        # First pass found nothing. Before giving up, check whether this
        # cluster looks like it fused multiple rows/tokens together (large
        # bbox relative to its own components) and retry with a much
        # stricter row-aware re-split.
        cx, cy, cw, ch = _cluster_bbox(cluster)
        subclusters = _resplit_cluster_by_rows(cluster)

        if len(subclusters) > 1:
            logger.info(
                "Cluster at (%d,%d) size %dx%d found nothing on first pass; "
                "row re-split into %d sub-cluster(s), retrying.",
                cx, cy, cw, ch, len(subclusters),
            )
            resplit_matches: List[PlaceholderMatch] = []
            all_resolved = True
            for sub_idx, sub in enumerate(subclusters):
                sub_matches = _ocr_cluster(labels, sub, idx, log_prefix=f"[resplit {sub_idx}] ")
                if sub_matches:
                    resplit_matches.extend(sub_matches)
                else:
                    all_resolved = False

            if resplit_matches:
                matches.extend(resplit_matches)
                if not all_resolved:
                    logger.warning(
                        "Cluster at (%d,%d): row re-split recovered %d of %d sub-cluster(s).",
                        cx, cy, len(resplit_matches), len(subclusters),
                    )
                continue

        # Still nothing: last resort, log both fallback reads for diagnosis.
        pil_img, _, _ = _render_cluster_canvas(labels, cluster)
        psm7_text = _ocr_single_token(pil_img, 7)
        psm8_text = _ocr_single_token(pil_img, 8)
        logger.warning(
            "Cluster at (%d,%d) size %dx%d produced no placeholder match "
            "(psm7='%s', psm8='%s') — skipping. Debug canvas saved under %s/",
            cx, cy, cw, ch, psm7_text, psm8_text, _DEBUG_DIR,
        )

    logger.info("OCR found %d placeholder(s) in image.", len(matches))
    return matches
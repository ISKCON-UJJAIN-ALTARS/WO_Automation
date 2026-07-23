import hashlib
import json
import logging
import os
import re
import shutil
import time
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

_DEBUG = os.environ.get("OCR_DEBUG", "0") == "1"

_PLACEHOLDER_RE = re.compile(r"\{([A-Z0-9_]+)\}")
_CHAR_WHITELIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789{}_"

_SAT_THRESHOLD = 50
_VAL_MIN = 30

_OPEN_KERNEL_SIZE = 2
_MIN_COMPONENT_AREA = 2
_MAX_COMPONENT_FRACTION = 0.15
_MAX_CLUSTER_ASPECT_RATIO = 20.0

# Upscale factor applied to each isolated placeholder crop before OCR.
_OCR_SCALE = 5

# Morphological close applied to each cluster's isolated mask before OCR.
# Anti-aliased/thin glyph pixels sometimes fall just under the saturation
# threshold in _colored_mask, leaving gappy strokes that read as blank or
# as only the bolder brace glyphs (e.g. OCR seeing '{}' with nothing
# inside). A small close reconnects those gaps without altering the
# overall shape enough to merge genuinely separate glyphs.
_CLOSE_KERNEL_SIZE = 3

# Two components are considered part of the SAME placeholder token only if
# they are close together AND similar in color. This is what keeps
# neighbouring-but-different labels (e.g. a green {H3} next to a purple
# {L3}) from being fused into one OCR read.
_COLOR_DIST_THRESHOLD = 55.0   # Euclidean distance in BGR space
_GAP_HEIGHT_MULTIPLIER = 1.6   # max horizontal gap, in units of ref comp height
_VERTICAL_ALIGN_FRACTION = 0.4  # max centroid y-difference, in units of ref comp height
# Reference height for both checks is min(a.h, b.h), not the average — one
# abnormally tall component (antialiasing bridge, stray bracket) can no
# longer inflate the tolerance and wrongly pull in a different row/token.

# Stricter pass used when a cluster's first OCR attempt finds nothing and
# we suspect it fused multiple rows/placeholders together geometrically.
_RESPLIT_VERTICAL_ALIGN_FRACTION = 0.15
_RESPLIT_GAP_HEIGHT_MULTIPLIER = 1.2

_CANVAS_PAD = 6

_DEBUG_DIR = "generated/ocr_debug_clusters"

# Loose fallback for keys: Tesseract frequently misreads '}' as '{' (near-
# mirror shapes at small sizes) or drops braces from the read while still
# reading the inner text correctly. Since clustering already guarantees one
# cluster == one placeholder, we don't need a perfect {KEY} regex match —
# just evidence this was a placeholder (a brace showed up somewhere) plus a
# clean alnum remainder to use as the key.
_LOOSE_KEY_RE = re.compile(r"^[A-Z0-9_]{1,8}$")

# Row grouping tolerance (fraction of average char height) used when
# splitting a cluster's OCR'd characters into rows for overlapping/stacked
# placeholders. Kept separate from the component-clustering constants
# above since it operates on Tesseract's own character boxes, not our
# connected components.
_CHAR_ROW_ALIGN_FRACTION = 0.6


# --------------------------------------------------------------------------
# Learning cache
#
# The same template file is rendered repeatedly with identical placeholder
# geometry/colors every time (only the substituted values change). There's
# no need to re-solve OCR for a cluster we've already resolved for this
# exact template. Each cluster gets a stable signature (bucketed position +
# size + color, tolerant to a few pixels of jitter) and, once resolved
# (either by a clean OCR read or a manual correction), that mapping is
# persisted to disk and reused on every future run — skipping OCR for that
# cluster entirely. Clusters that fail every OCR strategy are written to a
# "needs review" queue instead of just a warning that scrolls past in logs,
# so a human can supply the correct key once via apply_correction() and
# never see that failure again.
# --------------------------------------------------------------------------

_CACHE_DIR = "generated/ocr_cache"
_SIG_BUCKET_PX = 8     # position/size bucketing, in original-image pixels
_SIG_BUCKET_COLOR = 16  # color channel bucketing (0-255 -> 16 buckets)


def _safe_filename(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", key)


def _template_key_for_image(image: np.ndarray) -> str:
    """Stable identity for a template image. Same base template file ->
    same bytes -> same key, regardless of what filename it was loaded
    from, so the cache stays valid even if the template gets renamed or
    is referenced from multiple paths."""
    return hashlib.sha1(image.tobytes()).hexdigest()[:16]


def _cache_path(template_key: str) -> str:
    return os.path.join(_CACHE_DIR, f"{_safe_filename(template_key)}.json")


def _review_queue_path(template_key: str) -> str:
    return os.path.join(_CACHE_DIR, f"{_safe_filename(template_key)}.review.json")


def _cluster_signature(x: int, y: int, w: int, h: int, color: Tuple[int, int, int]) -> str:
    bx = (x // _SIG_BUCKET_PX) * _SIG_BUCKET_PX
    by = (y // _SIG_BUCKET_PX) * _SIG_BUCKET_PX
    bw = (w // _SIG_BUCKET_PX) * _SIG_BUCKET_PX
    bh = (h // _SIG_BUCKET_PX) * _SIG_BUCKET_PX
    bc = tuple(c // _SIG_BUCKET_COLOR for c in color)
    return f"{bx}_{by}_{bw}_{bh}_{bc[0]}_{bc[1]}_{bc[2]}"


def _load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to load %s; treating as empty.", path)
        return {}


def _save_json_atomic(path: str, data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp_path, path)
    except Exception:
        logger.exception("Failed to save %s", path)


def apply_correction(
    template_key: str, x: int, y: int, w: int, h: int, color: Tuple[int, int, int], key: str
) -> None:
    """Manually teach the cache the correct key for a cluster that OCR
    could not resolve (or resolved wrong). Use the (x, y, w, h, color)
    reported in a 'needs review' entry or a PlaceholderMatch. Persists
    immediately; every future detect_placeholders() call for this same
    template will use this key for that cluster without touching OCR."""
    sig = _cluster_signature(x, y, w, h, color)
    cache = _load_json(_cache_path(template_key))
    cache[sig] = {
        "key": key.upper(),
        "source": "manual",
        "corrected_at": time.time(),
        "hits": 0,
    }
    _save_json_atomic(_cache_path(template_key), cache)
    logger.info("Manual correction saved for template %s, signature %s -> {%s}", template_key, sig, key)

    # A manual correction resolves the failure — drop it from the review
    # queue if it's sitting there.
    review_path = _review_queue_path(template_key)
    queue = _load_json(review_path)
    if sig in queue:
        del queue[sig]
        _save_json_atomic(review_path, queue)


def list_unresolved(template_key: str) -> Dict[str, dict]:
    """Return the current 'needs review' queue for a template: signature
    -> {bbox, color, ocr attempts, debug canvas path}. Empty if everything
    has been resolved."""
    return _load_json(_review_queue_path(template_key))


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


def _bbox_overlap(a: dict, b: dict) -> bool:
    """True if two components' bounding boxes intersect at all. Used so
    genuinely overlapping/touching glyphs of the SAME color are always
    considered for merging regardless of the gap/alignment heuristics
    (which assume left-to-right non-overlapping layout)."""
    ax0, ay0, ax1, ay1 = a["x"], a["y"], a["x"] + a["w"], a["y"] + a["h"]
    bx0, by0, bx1, by1 = b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]
    return ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1


def _cluster_components(
    components: List[dict],
    vertical_align_fraction: float = _VERTICAL_ALIGN_FRACTION,
    gap_height_multiplier: float = _GAP_HEIGHT_MULTIPLIER,
) -> List[List[dict]]:
    """Group components into probable single-placeholder clusters using
    spatial proximity + color similarity, so that visually distinct
    placeholders never get merged even if they sit close together or their
    bounding boxes overlap.
    """
    n = len(components)
    uf = _UnionFind(n)
    for i in range(n):
        a = components[i]
        for j in range(i + 1, n):
            b = components[j]

            ca, cb = np.array(a["color"], dtype=float), np.array(b["color"], dtype=float)
            same_color = np.linalg.norm(ca - cb) <= _COLOR_DIST_THRESHOLD
            if not same_color:
                continue

            # Overlapping/touching bboxes of the same color are always the
            # same placeholder (e.g. glyphs that visually touch) — accept
            # immediately without the gap/alignment heuristics, which
            # assume a clean left-to-right, non-overlapping layout.
            if _bbox_overlap(a, b):
                uf.union(i, j)
                continue

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
    canvas, so OCR can never see a neighbouring placeholder's glyphs — even
    if that neighbour's bounding box overlaps this one. A small
    morphological close repairs thin/gappy strokes before upscaling."""
    H, W = labels.shape[:2]
    x0, y0, w, h = _cluster_bbox(cluster)
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(W, x0 + w + 2 * pad)
    y1 = min(H, y0 + h + 2 * pad)

    crop_labels = labels[y0:y1, x0:x1]
    label_ids = {c["label_id"] for c in cluster}
    cluster_mask = np.isin(crop_labels, list(label_ids)).astype(np.uint8) * 255

    close_kernel = np.ones((_CLOSE_KERNEL_SIZE, _CLOSE_KERNEL_SIZE), np.uint8)
    cluster_mask = cv2.morphologyEx(cluster_mask, cv2.MORPH_CLOSE, close_kernel)

    canvas = np.full((y1 - y0, x1 - x0, 3), 255, dtype=np.uint8)
    canvas[cluster_mask > 0] = (0, 0, 0)

    scale = _OCR_SCALE
    scaled = cv2.resize(
        canvas, (canvas.shape[1] * scale, canvas.shape[0] * scale),
        interpolation=cv2.INTER_CUBIC,
    )
    pil_img = Image.fromarray(cv2.cvtColor(scaled, cv2.COLOR_BGR2RGB))
    return pil_img, x0, y0


def _dump_debug_canvas(pil_img: Image.Image, idx: int, x0: int, y0: int, tag: str = "") -> None:
    if not _DEBUG:
        return
    try:
        os.makedirs(_DEBUG_DIR, exist_ok=True)
        suffix = f"_{tag}" if tag else ""
        path = os.path.join(_DEBUG_DIR, f"cluster_{idx:02d}_{x0}_{y0}{suffix}.png")
        pil_img.save(path)
    except Exception:
        logger.exception("Failed to write debug cluster canvas (idx=%d)", idx)


def _save_review_canvas(pil_img: Image.Image, template_key: str, sig: str) -> str:
    """Unlike _dump_debug_canvas, this always saves (not gated behind
    OCR_DEBUG) because it backs the persistent review queue that a human
    needs to actually look at to call apply_correction(). Returns the
    saved path so it can be recorded alongside the queue entry."""
    review_dir = os.path.join(_CACHE_DIR, _safe_filename(template_key), "review_canvases")
    try:
        os.makedirs(review_dir, exist_ok=True)
        path = os.path.join(review_dir, f"{sig}.png")
        pil_img.save(path)
        return path
    except Exception:
        logger.exception("Failed to save review canvas for signature %s", sig)
        return ""


def _ocr_single_token(pil_img: Image.Image, psm: int) -> str:
    text = pytesseract.image_to_string(
        pil_img, config=f"--psm {psm} -c tessedit_char_whitelist={_CHAR_WHITELIST}"
    )
    return text.strip()


def _ocr_with_fallbacks(pil_img: Image.Image) -> Tuple[str, int, List[Tuple[int, str]]]:
    """Try PSM modes 7 -> 8 -> 6 until one yields exactly one clean {KEY}
    match, stopping early. Returns (best_text, psm_used, all_attempts) so
    callers can reuse `all_attempts` for loose-key recovery or diagnostic
    logging without firing more Tesseract subprocess calls."""
    attempts: List[Tuple[int, str]] = []
    for psm in (7, 8, 6):
        text = _ocr_single_token(pil_img, psm)
        attempts.append((psm, text))
        if len(list(_PLACEHOLDER_RE.finditer(text))) == 1:
            return text, psm, attempts
    # No clean single match on any pass — return the first attempt as the
    # "primary" text (used for multi-match splitting / loose recovery).
    return attempts[0][1], attempts[0][0], attempts


def _extract_key_loose(raw_text: str) -> Optional[str]:
    """Recover a key when OCR read the inner text correctly but garbled the
    braces (e.g. '{A{' instead of '{A}', braces misread as mirror images of
    each other). Requires at least one brace character as evidence this was
    actually a placeholder, not arbitrary noise."""
    if "{" not in raw_text and "}" not in raw_text:
        return None
    stripped = raw_text.replace("{", "").replace("}", "").strip()
    if _LOOSE_KEY_RE.match(stripped):
        return stripped
    return None


def _char_boxes_for_crop(pil_crop: Image.Image) -> List[Tuple[str, int, int, int, int]]:
    """Per-character boxes via Tesseract, using sparse-text mode (psm 11)
    rather than single-line (psm 7). Sparse mode makes no assumption about
    a single text line, which is what lets the row-grouping step below
    correctly separate overlapping or vertically-stacked placeholders
    instead of interleaving their characters into a single garbled read."""
    img_w, img_h = pil_crop.size
    boxes_str = pytesseract.image_to_boxes(
        pil_crop, config=f"--psm 11 -c tessedit_char_whitelist={_CHAR_WHITELIST}"
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
    return entries


def _group_boxes_into_rows(
    entries: List[Tuple[str, int, int, int, int]]
) -> List[List[Tuple[str, int, int, int, int]]]:
    """Group character boxes into rows by vertical-center proximity, then
    sort each row left-to-right. This is what allows a single isolated
    cluster canvas to correctly resolve into MULTIPLE placeholders when
    they are stacked or overlapping, rather than assuming one text line."""
    if not entries:
        return []

    heights = [e[4] for e in entries if e[4] > 0]
    avg_h = (sum(heights) / len(heights)) if heights else 1.0

    # Sort by vertical center first so row-building below sweeps top to bottom.
    by_y = sorted(entries, key=lambda e: e[2] + e[4] / 2.0)

    rows: List[List[Tuple[str, int, int, int, int]]] = []
    for entry in by_y:
        cy = entry[2] + entry[4] / 2.0
        placed = False
        for row in rows:
            row_cy = sum(e[2] + e[4] / 2.0 for e in row) / len(row)
            if abs(cy - row_cy) <= avg_h * _CHAR_ROW_ALIGN_FRACTION:
                row.append(entry)
                placed = True
                break
        if not placed:
            rows.append([entry])

    for row in rows:
        row.sort(key=lambda e: e[1])

    rows.sort(key=lambda row: sum(e[2] for e in row) / len(row))
    return rows


def _split_cluster_into_tokens(
    pil_img: Image.Image, x0: int, y0: int, scale: int
) -> List[Tuple[str, int, int, int, int]]:
    """Row-aware fallback: a single color+proximity cluster still contains
    more than one {KEY} — e.g. two same-colored tokens close together,
    stacked vertically, or with overlapping bounding boxes. Character boxes
    are grouped into rows first (see _group_boxes_into_rows) so tokens on
    different rows are never interleaved into one garbled string."""
    entries = _char_boxes_for_crop(pil_img)
    if not entries:
        return []

    results: List[Tuple[str, int, int, int, int]] = []
    for row in _group_boxes_into_rows(entries):
        concat = "".join(e[0] for e in row)
        for m in _PLACEHOLDER_RE.finditer(concat):
            span = row[m.start(): m.end()]
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
    using a much stricter vertical-alignment tolerance. Recovers cases
    where the original pass geometrically fused two different rows into
    one oversized bbox that then OCR'd as garbage."""
    if len(cluster) < 2:
        return [cluster]
    return _cluster_components(
        cluster,
        vertical_align_fraction=_RESPLIT_VERTICAL_ALIGN_FRACTION,
        gap_height_multiplier=_RESPLIT_GAP_HEIGHT_MULTIPLIER,
    )


def _ocr_cluster(
    labels: np.ndarray, cluster: List[dict], idx: int, log_prefix: str = ""
) -> Tuple[List[PlaceholderMatch], List[Tuple[int, str]]]:
    """Run the full OCR pipeline against a single cluster: whole-canvas OCR
    first, then row-aware char-box splitting, then loose brace recovery.
    Returns (matches, diagnostic_attempts) — the latter lets the caller log
    a useful failure message without firing extra Tesseract calls."""
    pil_img, x0, y0 = _render_cluster_canvas(labels, cluster)
    _dump_debug_canvas(pil_img, idx, x0, y0, tag=log_prefix)

    raw_text, psm_used, attempts = _ocr_with_fallbacks(pil_img)
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
        return matches, attempts

    # Zero or multiple matches on the flat read: try row-aware splitting.
    # This is the general path that also covers overlapping/stacked
    # placeholders, not just the ">1 matches" case.
    split = _split_cluster_into_tokens(pil_img, x0, y0, _OCR_SCALE)
    if split:
        if len(found) > 1:
            logger.warning(
                "%sCluster at (%d,%d) OCR'd as '%s' — multiple placeholders, splitting.",
                log_prefix, cx, cy, raw_text,
            )
        else:
            logger.info(
                "%sCluster at (%d,%d) flat OCR found nothing ('%s'); "
                "row-aware split recovered %d token(s).",
                log_prefix, cx, cy, raw_text, len(split),
            )
        for key, sx, sy, sw, sh in split:
            token = "{" + key + "}"
            matches.append(PlaceholderMatch(token=token, key=key, x=sx, y=sy, w=sw, h=sh, color=color))
            logger.debug("%sSplit cluster -> %s at (%d,%d)", log_prefix, token, sx, sy)
        return matches, attempts

    if len(found) > 1:
        # Splitting failed but the flat read did contain multiple {KEY}s —
        # keep them merged at the cluster's bbox rather than losing them.
        logger.warning(
            "%sCould not split cluster '%s' into rows; keeping merged tokens as-is.",
            log_prefix, raw_text,
        )
        for m in found:
            key = m.group(1)
            token = "{" + key + "}"
            matches.append(PlaceholderMatch(token=token, key=key, x=cx, y=cy, w=cw, h=ch, color=color))
        return matches, attempts

    # Nothing from the flat read and nothing to split. Last resort: loose
    # brace-stripped recovery across every attempt already made.
    for _, text in attempts:
        loose_key = _extract_key_loose(text)
        if loose_key:
            token = "{" + loose_key + "}"
            matches.append(PlaceholderMatch(token=token, key=loose_key, x=cx, y=cy, w=cw, h=ch, color=color))
            logger.info(
                "%sCluster at (%d,%d) recovered via loose brace-stripped match: raw='%s' -> %s",
                log_prefix, cx, cy, text, token,
            )
            return matches, attempts

    return matches, attempts  # empty: caller decides what to try next


def detect_placeholders(image: np.ndarray, template_key: Optional[str] = None) -> List[PlaceholderMatch]:
    """Detect {KEY} placeholders in a rendered template image.

    template_key identifies which learning cache to use. If omitted, it's
    derived from the image bytes themselves, so re-renders of the exact
    same template automatically reuse whatever this function (or a manual
    apply_correction() call) has already learned about that template's
    placeholders — without needing the caller to pass anything special.
    """
    if template_key is None:
        template_key = _template_key_for_image(image)

    cache = _load_json(_cache_path(template_key))
    review_queue = _load_json(_review_queue_path(template_key))
    cache_dirty = False
    review_dirty = False

    labels, keep_mask, components = _connected_components(image)

    if _DEBUG:
        debug_mask = np.full_like(image, 255)
        debug_mask[keep_mask] = (0, 0, 0)
        os.makedirs("generated", exist_ok=True)
        cv2.imwrite("generated/ocr_debug.png", debug_mask)

    clusters = _cluster_components(components)
    clusters = _filter_clusters(clusters, image.shape)
    logger.info("Formed %d candidate placeholder cluster(s) from %d component(s).",
                len(clusters), len(components))

    matches: List[PlaceholderMatch] = []
    cache_hits = 0

    def _try_cache(cx: int, cy: int, cw: int, ch: int, color: Tuple[int, int, int]) -> Optional[PlaceholderMatch]:
        sig = _cluster_signature(cx, cy, cw, ch, color)
        entry = cache.get(sig)
        if entry is None:
            return None
        nonlocal cache_dirty
        entry["hits"] = entry.get("hits", 0) + 1
        cache_dirty = True
        key = entry["key"]
        return PlaceholderMatch(token="{" + key + "}", key=key, x=cx, y=cy, w=cw, h=ch, color=color)

    def _record_resolved(cx: int, cy: int, cw: int, ch: int, color: Tuple[int, int, int], key: str) -> None:
        nonlocal cache_dirty
        sig = _cluster_signature(cx, cy, cw, ch, color)
        # Don't clobber an existing manual correction with a fresh OCR read.
        if cache.get(sig, {}).get("source") == "manual":
            return
        cache[sig] = {"key": key, "source": "ocr_auto", "hits": 1}
        cache_dirty = True
        # A resolved cluster is no longer unresolved.
        sig_in_queue = sig in review_queue
        if sig_in_queue:
            del review_queue[sig]
            nonlocal review_dirty
            review_dirty = True

    def _record_unresolved(labels_, cluster_, cx: int, cy: int, cw: int, ch: int,
                            color: Tuple[int, int, int], attempt_summary: str) -> None:
        nonlocal review_dirty
        sig = _cluster_signature(cx, cy, cw, ch, color)
        pil_img, _, _ = _render_cluster_canvas(labels_, cluster_)
        canvas_path = _save_review_canvas(pil_img, template_key, sig)
        review_queue[sig] = {
            "x": cx, "y": cy, "w": cw, "h": ch, "color": list(color),
            "ocr_attempts": attempt_summary,
            "canvas_path": canvas_path,
            "last_seen": time.time(),
        }
        review_dirty = True

    for idx, cluster in enumerate(clusters):
        cx, cy, cw, ch = _cluster_bbox(cluster)
        color = _cluster_color(cluster)

        cached_match = _try_cache(cx, cy, cw, ch, color)
        if cached_match is not None:
            matches.append(cached_match)
            cache_hits += 1
            continue

        cluster_matches, attempts = _ocr_cluster(labels, cluster, idx)

        if cluster_matches:
            matches.extend(cluster_matches)
            if len(cluster_matches) == 1:
                _record_resolved(cx, cy, cw, ch, color, cluster_matches[0].key)
            continue

        # First pass found nothing. Check whether this cluster looks like
        # it fused multiple rows/tokens together geometrically and retry
        # with a much stricter row-aware component re-split.
        subclusters = _resplit_cluster_by_rows(cluster)

        if len(subclusters) > 1:
            logger.info(
                "Cluster at (%d,%d) size %dx%d found nothing on first pass; "
                "row re-split into %d sub-cluster(s), retrying.",
                cx, cy, cw, ch, len(subclusters),
            )
            resplit_matches: List[PlaceholderMatch] = []
            resolved_count = 0
            for sub_idx, sub in enumerate(subclusters):
                sub_matches, _ = _ocr_cluster(labels, sub, idx, log_prefix=f"[resplit {sub_idx}] ")
                if sub_matches:
                    resolved_count += 1
                    resplit_matches.extend(sub_matches)
                    if len(sub_matches) == 1:
                        sx, sy, sw, sh = _cluster_bbox(sub)
                        _record_resolved(sx, sy, sw, sh, _cluster_color(sub), sub_matches[0].key)

            if resplit_matches:
                matches.extend(resplit_matches)
                if resolved_count < len(subclusters):
                    logger.warning(
                        "Cluster at (%d,%d): row re-split recovered %d of %d sub-cluster(s).",
                        cx, cy, resolved_count, len(subclusters),
                    )
                continue

        # Still nothing: log using attempts already made, no extra OCR
        # calls, and queue it for a one-time manual correction so it never
        # has to be blindly re-attempted on every future render.
        attempt_summary = ", ".join(f"psm{p}='{t}'" for p, t in attempts)
        logger.warning(
            "Cluster at (%d,%d) size %dx%d produced no placeholder match (%s) — skipping. "
            "Queued for review (template %s).",
            cx, cy, cw, ch, attempt_summary, template_key,
        )
        _record_unresolved(labels, cluster, cx, cy, cw, ch, color, attempt_summary)

    if cache_dirty:
        _save_json_atomic(_cache_path(template_key), cache)
    if review_dirty:
        _save_json_atomic(_review_queue_path(template_key), review_queue)

    if cache_hits:
        logger.info("%d placeholder(s) resolved from learning cache (template %s), no OCR needed.",
                    cache_hits, template_key)

    unresolved_count = len(review_queue)
    logger.info(
        "OCR found %d placeholder(s) in image (%d from cache, %d needing review under %s).",
        len(matches), cache_hits, unresolved_count, os.path.join(_CACHE_DIR, _safe_filename(template_key)),
    )
    return matches
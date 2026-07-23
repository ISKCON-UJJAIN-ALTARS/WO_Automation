import hashlib
import json
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import cv2
import numpy as np
import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)

pytesseract.pytesseract.tesseract_cmd = (
    os.environ.get("TESSERACT_CMD") or shutil.which("tesseract") or r"D:\New folder\tesseract.exe"
)

_DEBUG = os.environ.get("OCR_DEBUG", "0") == "1"

_PLACEHOLDER_RE = re.compile(r"\{([A-Z0-9_]+)\}")
_LOOSE_KEY_RE = re.compile(r"^[A-Z0-9_]{1,8}$")
_CHAR_WHITELIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789{}_"

# Confirmed real placeholder vocabulary (from the app's actual output
# mappings). Used as a safety-net allow-list whenever the caller doesn't
# pass output_mapping through. Extended with L1/D1 since those are
# legitimate keys.
_DEFAULT_KNOWN_KEYS: Set[str] = {
    "A", "B", "W", "S", "N", "FL", "L", "H", "X", "SL", "ML", "SH", "V", "D", "L1", "D1",
}

# Detection / clustering tuning
_SAT_THRESHOLD, _VAL_MIN = 50, 30
# Black/dark-gray placeholder text (e.g. plain "{L}" style labels, as
# opposed to the colored dimension labels) has near-zero saturation, so
# _SAT_THRESHOLD alone never sees it — S = (max-min)/max is ~0 for any
# grayscale pixel regardless of how dark it is. _DARK_VAL_MAX catches those
# separately: any sufficiently dark pixel counts as "ink" even with no
# saturation. Kept well below the near-white background level so faint
# anti-aliasing/JPEG noise near white doesn't get swept in.
_DARK_VAL_MAX = 80
_OPEN_KERNEL_SIZE, _CLOSE_KERNEL_SIZE = 2, 3
# Thin-line stripping for the dark channel (see _strip_thin_lines). Must be
# longer than any single glyph's own stroke run (so a "1" or "L" doesn't
# get eroded away) but shorter than the shortest real dimension-line shaft
# in these templates, so straight shafts get isolated and removed while
# character strokes survive untouched.
_LINE_STRIP_KERNEL_LEN = 22
_MIN_COMPONENT_AREA = 2
_MAX_COMPONENT_FRACTION = 0.15
_MAX_CLUSTER_ASPECT_RATIO = 20.0
_COLOR_DIST_THRESHOLD = 55.0
_GAP_HEIGHT_MULTIPLIER, _VERTICAL_ALIGN_FRACTION = 1.6, 0.4      # first-pass clustering
_RESPLIT_GAP_HEIGHT_MULTIPLIER, _RESPLIT_VERTICAL_ALIGN_FRACTION = 1.2, 0.15  # stricter retry
_CHAR_ROW_ALIGN_FRACTION = 0.6
_OCR_SCALE = 5
_CANVAS_PAD = 6
_TIER2_TRUSTED_PSMS = (8, 10)  # single-word/single-char modes trusted for no-brace recovery
_ARROW_SATELLITE_DILATE_PX = 4  # how close a stray component must be to a flagged arrow/line to be absorbed into it

_DEBUG_DIR = "generated/ocr_debug_clusters"
_CACHE_DIR = "generated/ocr_cache"
_SIG_BUCKET_PX, _SIG_BUCKET_COLOR = 8, 16

# Confidence ranking for competing matches of the SAME key when the output
# mapping says only N of them should exist (see _validate_counts). Lower
# rank == more trustworthy.
_SOURCE_RANK = {
    "cache": 0,
    "direct": 1,
    "split": 2,
    "merged": 3,
    "tier1": 4,
    "tier2": 5,
}


@dataclass
class PlaceholderMatch:
    token: str
    key: str
    x: int
    y: int
    w: int
    h: int
    color: Tuple[int, int, int]
    source: str = "unknown"


# --------------------------------------------------------------------------
# Learning cache
# --------------------------------------------------------------------------

def _safe_filename(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", key)


def _template_key_for_image(image: np.ndarray) -> str:
    return hashlib.sha1(image.tobytes()).hexdigest()[:16]


def _cache_path(tk: str) -> str:
    return os.path.join(_CACHE_DIR, f"{_safe_filename(tk)}.json")


def _review_path(tk: str) -> str:
    return os.path.join(_CACHE_DIR, f"{_safe_filename(tk)}.review.json")


def _cluster_signature(x: int, y: int, w: int, h: int, color: Tuple[int, int, int]) -> str:
    bx, by, bw, bh = (v // _SIG_BUCKET_PX * _SIG_BUCKET_PX for v in (x, y, w, h))
    bc = tuple(c // _SIG_BUCKET_COLOR for c in color)
    return f"{bx}_{by}_{bw}_{bh}_{bc[0]}_{bc[1]}_{bc[2]}"


def _load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to load %s", path)
        return {}


def _save_json(path: str, data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        logger.exception("Failed to save %s", path)


def apply_correction(tk: str, x: int, y: int, w: int, h: int, color: Tuple[int, int, int], key: str) -> None:
    """Manually teach the cache the correct key for a cluster OCR couldn't
    resolve. Every future detect_placeholders() call for this template
    uses it without touching OCR again."""
    sig = _cluster_signature(x, y, w, h, color)
    cache = _load_json(_cache_path(tk))
    cache[sig] = {"key": key.upper(), "source": "manual", "corrected_at": time.time(), "hits": 0}
    _save_json(_cache_path(tk), cache)

    queue = _load_json(_review_path(tk))
    if sig in queue:
        del queue[sig]
        _save_json(_review_path(tk), queue)
    logger.info("Manual correction saved: template=%s sig=%s -> {%s}", tk, sig, key)


def list_unresolved(tk: str) -> Dict[str, dict]:
    """signature -> {bbox, color, ocr attempts, debug canvas path} for
    everything still awaiting a manual correction."""
    return _load_json(_review_path(tk))


# --------------------------------------------------------------------------
# Component detection + clustering
# --------------------------------------------------------------------------

def _strip_thin_lines(mask_u8: np.ndarray) -> np.ndarray:
    """Remove long, straight horizontal/vertical line segments (dimension
    shafts) from an ink mask WITHOUT eroding compact glyph strokes.

    A directional morphological opening only lets pixels survive if they
    belong to an unbroken straight run at least as long as the kernel. Pick
    the kernel longer than any single glyph's own stroke run (so a "1", an
    "L"'s vertical, etc. never survive the opening and are therefore never
    classified as "line") but shorter than the shortest real dimension-line
    shaft in these templates (so shafts reliably do survive and get
    isolated). What survives the opening is the line; it's subtracted back
    out of the original mask, leaving everything else — including short
    strokes — untouched.

    This exists because plain black/dark dimension-line shafts sitting
    right next to (or touching) a same-toned placeholder label become ONE
    connected component at the pixel level before any clustering logic
    runs. Once fused like that, nothing downstream (resplitting, tier-1/2
    recovery) can separate them again — this has to happen before
    connectedComponentsWithStats ever sees the mask.
    """
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (_LINE_STRIP_KERNEL_LEN, 1))
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, _LINE_STRIP_KERNEL_LEN))
    h_lines = cv2.morphologyEx(mask_u8, cv2.MORPH_OPEN, h_kernel)
    v_lines = cv2.morphologyEx(mask_u8, cv2.MORPH_OPEN, v_kernel)
    lines = cv2.bitwise_or(h_lines, v_lines)
    return cv2.subtract(mask_u8, lines)


def _ink_masks(image: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Two separate masks: clearly colored (saturated) pixels, and dark
    (black/gray) pixels regardless of saturation. Kept separate rather than
    immediately combined because they need different noise handling — see
    _connected_components."""
    h, s, v = cv2.split(cv2.cvtColor(image, cv2.COLOR_BGR2HSV))
    is_colored = (s > _SAT_THRESHOLD) & (v > _VAL_MIN)
    is_dark = v < _DARK_VAL_MAX
    return is_colored, is_dark


def _colored_mask(image: np.ndarray) -> np.ndarray:
    """Combined placeholder-ink mask (colored OR dark), for debug
    visualization only — see _connected_components for why the two
    channels are treated differently before being combined for real use."""
    is_colored, is_dark = _ink_masks(image)
    return is_colored | is_dark


def _connected_components(image: np.ndarray) -> Tuple[np.ndarray, np.ndarray, List[dict]]:
    is_colored, is_dark = _ink_masks(image)

    colored_u8 = is_colored.astype(np.uint8) * 255
    colored_opened = cv2.morphologyEx(
        colored_u8, cv2.MORPH_OPEN, np.ones((_OPEN_KERNEL_SIZE,) * 2, np.uint8)
    )

    # Dark/black text is NOT run through the small square opening used for
    # the colored channel: that kernel is sized for saturation-threshold
    # speckle noise, and applying it here would erode genuinely thin glyph
    # strokes (a digit "1" is often only 1-2px wide) — that was silently
    # deleting characters outright, e.g. "{L1}" losing its "1" (and often
    # most of "L") entirely.
    #
    # But skipping ALL noise handling on this channel means a plain black
    # dimension-line shaft that touches a black/dark label fuses into one
    # connected component with it, with zero separation — that's what was
    # producing "{L1}"/"{D1}" style labels emitting blank or garbled OCR
    # ('SEE', 'EE', 'S', 'SC') despite every other key resolving fine: the
    # line + text were literally one blob before clustering ever started.
    # _strip_thin_lines targets exactly the shaft (a long straight run)
    # without touching short glyph strokes, so it's safe where blanket
    # opening wasn't.
    dark_u8 = _strip_thin_lines(is_dark.astype(np.uint8) * 255)

    mask = cv2.bitwise_or(colored_opened, dark_u8)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    img_h, img_w = mask.shape[:2]

    keep_ids = [
        i for i in range(1, num_labels)
        if stats[i][4] >= _MIN_COMPONENT_AREA
        and stats[i][2] <= _MAX_COMPONENT_FRACTION * img_w
        and stats[i][3] <= _MAX_COMPONENT_FRACTION * img_h
    ]
    keep_mask = np.isin(labels, keep_ids) if keep_ids else np.zeros(mask.shape, dtype=bool)

    components = []
    for i in keep_ids:
        x, y, w, h, area = stats[i]
        pixels = image[labels == i]
        color = tuple(int(v) for v in np.median(pixels.reshape(-1, 3), axis=0)) if pixels.size else (0, 0, 0)
        components.append({"label_id": i, "x": int(x), "y": int(y), "w": int(w), "h": int(h),
                            "area": int(area), "color": color})
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
    return (a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"]
            and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"])


def _cluster_components(components: List[dict], vertical_align_fraction: float = _VERTICAL_ALIGN_FRACTION,
                         gap_height_multiplier: float = _GAP_HEIGHT_MULTIPLIER) -> List[List[dict]]:
    """Group same-colored, spatially-close components into one placeholder
    each. Overlapping/touching same-color bboxes always merge outright;
    otherwise merge only if vertically aligned and horizontally close,
    using min(height) as the reference so one oversized component can't
    inflate tolerance and bridge a different row."""
    n = len(components)
    uf = _UnionFind(n)
    for i in range(n):
        a = components[i]
        for j in range(i + 1, n):
            b = components[j]
            if np.linalg.norm(np.array(a["color"], float) - np.array(b["color"], float)) > _COLOR_DIST_THRESHOLD:
                continue
            if _bbox_overlap(a, b):
                uf.union(i, j)
                continue
            ref_h = min(a["h"], b["h"])
            if ref_h <= 0:
                continue
            if abs((a["y"] + a["h"] / 2) - (b["y"] + b["h"] / 2)) > ref_h * vertical_align_fraction:
                continue
            gap = (b["x"] - (a["x"] + a["w"])) if a["x"] <= b["x"] else (a["x"] - (b["x"] + b["w"]))
            if gap > ref_h * gap_height_multiplier:
                continue
            uf.union(i, j)

    groups: Dict[int, List[dict]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(components[i])
    return list(groups.values())


def _resplit_cluster_by_rows(cluster: List[dict]) -> List[List[dict]]:
    """Retry a cluster that OCR'd as garbage with a much stricter
    tolerance, in case it geometrically fused two different rows."""
    if len(cluster) < 2:
        return [cluster]
    return _cluster_components(cluster, _RESPLIT_VERTICAL_ALIGN_FRACTION, _RESPLIT_GAP_HEIGHT_MULTIPLIER)


def _cluster_bbox(cluster: List[dict]) -> Tuple[int, int, int, int]:
    xs, ys = [c["x"] for c in cluster], [c["y"] for c in cluster]
    x2s, y2s = [c["x"] + c["w"] for c in cluster], [c["y"] + c["h"] for c in cluster]
    x0, y0 = min(xs), min(ys)
    return x0, y0, max(x2s) - x0, max(y2s) - y0


def _cluster_color(cluster: List[dict]) -> Tuple[int, int, int]:
    return tuple(int(v) for v in np.median(np.array([c["color"] for c in cluster], float), axis=0))


def _filter_clusters(clusters: List[List[dict]], img_shape: Tuple[int, int]) -> List[List[dict]]:
    img_h, img_w = img_shape[:2]
    kept = []
    for cluster in clusters:
        _, _, w, h = _cluster_bbox(cluster)
        if w > _MAX_COMPONENT_FRACTION * img_w or h > _MAX_COMPONENT_FRACTION * img_h:
            continue
        if len(cluster) == 1 and max(w, h) / max(min(w, h), 1) > _MAX_CLUSTER_ASPECT_RATIO:
            continue
        kept.append(cluster)
    return kept


# --------------------------------------------------------------------------
# Output-mapping / allow-list validation
# --------------------------------------------------------------------------

def _normalize_output_mapping(
    output_mapping: Optional[Dict[str, object]]
) -> Tuple[Optional[Set[str]], Dict[str, int]]:
    if not output_mapping:
        return None, {}

    allowed_keys: Set[str] = set()
    expected_counts: Dict[str, int] = {}

    for raw_key, raw_count in output_mapping.items():
        key = str(raw_key).strip().upper()
        if not _LOOSE_KEY_RE.match(key):
            continue
        allowed_keys.add(key)
        try:
            count = int(raw_count)
            if count >= 0:
                expected_counts[key] = count
        except (TypeError, ValueError):
            pass

    return allowed_keys, expected_counts


def _is_allowed_key(key: str, allowed_keys: Optional[Set[str]]) -> bool:
    """If no output mapping is supplied, fall back to the confirmed known
    placeholder vocabulary rather than allowing anything through."""
    normalized = key.strip().upper()
    effective_keys = allowed_keys if allowed_keys is not None else _DEFAULT_KNOWN_KEYS
    return normalized in effective_keys


def _component_features(component: dict) -> Tuple[float, float]:
    w = max(int(component["w"]), 1)
    h = max(int(component["h"]), 1)
    area = max(int(component["area"]), 0)
    aspect_ratio = max(w, h) / max(min(w, h), 1)
    fill_ratio = area / float(w * h)
    return aspect_ratio, fill_ratio


def _is_obvious_graphic_component(component: dict) -> bool:
    """Reject components overwhelmingly likely to be drawing graphics
    (dimension arrows, leader lines, filled rectangles) rather than text.
    Conservative on purpose — only very obvious graphics are rejected;
    arrowheads that slip through here are caught relationally by
    _mark_arrow_satellites instead."""
    aspect_ratio, fill_ratio = _component_features(component)
    w = int(component["w"])
    h = int(component["h"])

    if aspect_ratio >= 12.0:
        return True

    if w >= 15 and h >= 15 and fill_ratio <= 0.12:
        return True

    if w >= 12 and h >= 8 and fill_ratio >= 0.92:
        return True

    return False


def _mark_arrow_satellites(
    all_components: List[dict], graphic_ids: Set[int], dilate_px: int = _ARROW_SATELLITE_DILATE_PX
) -> Set[int]:
    """Catch arrowheads that _is_obvious_graphic_component misses: small,
    ~50% filled, roughly square, physically touching an already-flagged
    same-color shaft/line."""
    graphics = [c for c in all_components if c["label_id"] in graphic_ids]
    if not graphics:
        return set()

    extra: Set[int] = set()
    for c in all_components:
        if c["label_id"] in graphic_ids:
            continue
        for g in graphics:
            if np.linalg.norm(np.array(c["color"], float) - np.array(g["color"], float)) > _COLOR_DIST_THRESHOLD:
                continue
            gx0, gy0 = g["x"] - dilate_px, g["y"] - dilate_px
            gx1, gy1 = g["x"] + g["w"] + dilate_px, g["y"] + g["h"] + dilate_px
            if c["x"] < gx1 and gx0 < c["x"] + c["w"] and c["y"] < gy1 and gy0 < c["y"] + c["h"]:
                extra.add(c["label_id"])
                break
    return extra


def _validate_counts(
    matches: List[PlaceholderMatch], expected_counts: Dict[str, int]
) -> List[PlaceholderMatch]:
    """Trim excess matches for a key beyond what the output mapping
    expects, dropping the lowest-confidence ones first (see _SOURCE_RANK)."""
    if not expected_counts:
        return matches

    by_key: Dict[str, List[PlaceholderMatch]] = {}
    for m in matches:
        by_key.setdefault(m.key, []).append(m)

    keep: List[PlaceholderMatch] = []
    for key, group in by_key.items():
        expected = expected_counts.get(key)
        if expected is None or len(group) <= expected:
            keep.extend(group)
            continue

        group_sorted = sorted(group, key=lambda m: _SOURCE_RANK.get(m.source, 99))
        survivors, dropped = group_sorted[:expected], group_sorted[expected:]
        keep.extend(survivors)
        for d in dropped:
            logger.warning(
                "Key {%s}: found %d candidate(s), expected %d — dropping lower-confidence "
                "match at (%d,%d) [source=%s].",
                key, len(group), expected, d.x, d.y, d.source,
            )
    return keep


# --------------------------------------------------------------------------
# Rendering + OCR
# --------------------------------------------------------------------------

def _render_cluster_canvas(labels: np.ndarray, cluster: List[dict], pad: int = _CANVAS_PAD
                            ) -> Tuple[Image.Image, int, int]:
    """Isolate only this cluster's pixels on a white canvas (immune to
    overlapping neighbours since it's mask-based, not bbox-crop-based),
    close small gaps in thin strokes, then upscale for OCR."""
    H, W = labels.shape[:2]
    x0, y0, w, h = _cluster_bbox(cluster)
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1, y1 = min(W, x0 + w + 2 * pad), min(H, y0 + h + 2 * pad)

    crop = labels[y0:y1, x0:x1]
    label_ids = {c["label_id"] for c in cluster}
    mask = np.isin(crop, list(label_ids)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((_CLOSE_KERNEL_SIZE,) * 2, np.uint8))

    canvas = np.full((y1 - y0, x1 - x0, 3), 255, dtype=np.uint8)
    canvas[mask > 0] = (0, 0, 0)
    scaled = cv2.resize(canvas, (canvas.shape[1] * _OCR_SCALE, canvas.shape[0] * _OCR_SCALE),
                         interpolation=cv2.INTER_CUBIC)
    return Image.fromarray(cv2.cvtColor(scaled, cv2.COLOR_BGR2RGB)), x0, y0


def _save_canvas(pil_img: Image.Image, path: str) -> str:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        pil_img.save(path)
        return path
    except Exception:
        logger.exception("Failed to save canvas %s", path)
        return ""


def _ocr_text(pil_img: Image.Image, psm: int) -> str:
    return pytesseract.image_to_string(
        pil_img, config=f"--psm {psm} -c tessedit_char_whitelist={_CHAR_WHITELIST}"
    ).strip()


def _ocr_with_fallbacks(pil_img: Image.Image) -> Tuple[str, int, List[Tuple[int, str]]]:
    attempts = []
    for psm in (7, 8, 6, 10):
        text = _ocr_text(pil_img, psm)
        attempts.append((psm, text))
        if len(list(_PLACEHOLDER_RE.finditer(text))) == 1:
            return text, psm, attempts
    return attempts[0][1], attempts[0][0], attempts


def _extract_key_loose(raw_text: str) -> Optional[str]:
    if "{" not in raw_text and "}" not in raw_text:
        return None
    stripped = raw_text.replace("{", "").replace("}", "").strip()
    return stripped if _LOOSE_KEY_RE.match(stripped) else None


def _extract_key_bare(psm: int, text: str) -> Optional[str]:
    if psm not in _TIER2_TRUSTED_PSMS:
        return None
    stripped = text.strip()
    if not stripped or set(stripped) == {"_"}:
        return None
    return stripped if _LOOSE_KEY_RE.match(stripped) and len(stripped) <= 4 else None


def _char_boxes(pil_crop: Image.Image) -> List[Tuple[str, int, int, int, int]]:
    img_w, img_h = pil_crop.size
    boxes_str = pytesseract.image_to_boxes(
        pil_crop, config=f"--psm 11 -c tessedit_char_whitelist={_CHAR_WHITELIST}"
    )
    entries = []
    for line in boxes_str.strip().splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        ch, left, bottom, right, top = parts[0], *(int(p) for p in parts[1:5])
        entries.append((ch, left, img_h - top, right - left, top - bottom))
    return entries


def _group_into_rows(entries: List[Tuple[str, int, int, int, int]]) -> List[List[Tuple[str, int, int, int, int]]]:
    if not entries:
        return []
    heights = [e[4] for e in entries if e[4] > 0]
    avg_h = (sum(heights) / len(heights)) if heights else 1.0

    rows: List[List[Tuple[str, int, int, int, int]]] = []
    for entry in sorted(entries, key=lambda e: e[2] + e[4] / 2):
        cy = entry[2] + entry[4] / 2
        for row in rows:
            if abs(cy - sum(e[2] + e[4] / 2 for e in row) / len(row)) <= avg_h * _CHAR_ROW_ALIGN_FRACTION:
                row.append(entry)
                break
        else:
            rows.append([entry])

    for row in rows:
        row.sort(key=lambda e: e[1])
    rows.sort(key=lambda row: sum(e[2] for e in row) / len(row))
    return rows


def _split_cluster_into_tokens(pil_img: Image.Image, x0: int, y0: int, scale: int
                                ) -> List[Tuple[str, int, int, int, int]]:
    entries = _char_boxes(pil_img)
    if not entries:
        return []
    results = []
    for row in _group_into_rows(entries):
        concat = "".join(e[0] for e in row)
        for m in _PLACEHOLDER_RE.finditer(concat):
            span = row[m.start(): m.end()]
            if not span:
                continue
            xs, ys = [e[1] for e in span], [e[2] for e in span]
            x2s, y2s = [e[1] + e[3] for e in span], [e[2] + e[4] for e in span]
            bx, by = min(xs), min(ys)
            results.append((m.group(1), x0 + bx // scale, y0 + by // scale,
                             (max(x2s) - bx) // scale, (max(y2s) - by) // scale))
    return results


def _ocr_cluster(labels: np.ndarray, cluster: List[dict], idx: int, tag: str = "",
                  allowed_keys: Optional[Set[str]] = None
                  ) -> Tuple[List[PlaceholderMatch], List[Tuple[int, str]]]:
    """Full pipeline for one cluster: direct OCR -> row-aware split ->
    merged multi-match -> tier-1 brace-garbled recovery -> tier-2 bare
    recovery (requires psm 8/10 agreement)."""
    pil_img, x0, y0 = _render_cluster_canvas(labels, cluster)
    if _DEBUG:
        _save_canvas(pil_img, os.path.join(_DEBUG_DIR, f"cluster_{idx:02d}_{x0}_{y0}{'_' + tag if tag else ''}.png"))

    raw_text, psm_used, attempts = _ocr_with_fallbacks(pil_img)
    found = list(_PLACEHOLDER_RE.finditer(raw_text))
    cx, cy, cw, ch = _cluster_bbox(cluster)
    color = _cluster_color(cluster)
    matches: List[PlaceholderMatch] = []

    direct_match: Optional[PlaceholderMatch] = None
    expected_components = 0
    if len(found) == 1:
        key = found[0].group(1).upper()
        expected_components = len(found[0].group(1)) + 2  # braces + ~1 component/char
        if _is_allowed_key(key, allowed_keys):
            direct_match = PlaceholderMatch("{" + key + "}", key, cx, cy, cw, ch, color, source="direct")
        else:
            logger.info(
                "%sCluster at (%d,%d): rejected OCR key {%s}; not in output mappings — trying recovery.",
                tag, cx, cy, key
            )

    # A cluster with far more components than its single matched key needs
    # (braces + ~1/char) likely swallowed a second token. Don't accept the
    # direct match at face value in that case; verify via row-aware split
    # first so a silently-dropped placeholder gets a chance to be
    # recovered instead of just disappearing.
    looks_like_multiple_tokens = direct_match is not None and len(cluster) > expected_components + 2

    if direct_match is not None and not looks_like_multiple_tokens:
        matches.append(direct_match)
        return matches, attempts

    if looks_like_multiple_tokens:
        logger.info(
            "%sCluster at (%d,%d): direct read {%s} but %d component(s) (~%d expected) — "
            "checking for an additional merged token before accepting.",
            tag, cx, cy, direct_match.key, len(cluster), expected_components,
        )

    split = _split_cluster_into_tokens(pil_img, x0, y0, _OCR_SCALE)
    if split:
        for key, sx, sy, sw, sh in split:
            key = key.upper()
            if not _is_allowed_key(key, allowed_keys):
                logger.info("%sCluster at (%d,%d): rejected split OCR key {%s}.", tag, cx, cy, key)
                continue
            matches.append(PlaceholderMatch("{" + key + "}", key, sx, sy, sw, sh, color, source="split"))
        if direct_match is not None and not any(m.key == direct_match.key for m in matches):
            matches.append(direct_match)
        if matches:
            logger.info("%sCluster at (%d,%d): split into %d valid token(s) (raw='%s')",
                        tag, cx, cy, len(matches), raw_text)
            return matches, attempts

    if direct_match is not None:
        matches.append(direct_match)
        return matches, attempts

    if len(found) > 1:
        for m in found:
            key = m.group(1).upper()
            if not _is_allowed_key(key, allowed_keys):
                logger.info("%sCluster at (%d,%d): rejected merged OCR key {%s}.", tag, cx, cy, key)
                continue
            matches.append(PlaceholderMatch("{" + key + "}", key, cx, cy, cw, ch, color, source="merged"))
        if matches:
            logger.warning("%sCluster at (%d,%d): couldn't split '%s', kept valid matches.", tag, cx, cy, raw_text)
            return matches, attempts

    for _, text in attempts:
        loose = _extract_key_loose(text)
        if loose is None:
            continue
        loose = loose.upper()
        if _is_allowed_key(loose, allowed_keys):
            matches.append(PlaceholderMatch("{" + loose + "}", loose, cx, cy, cw, ch, color, source="tier1"))
            logger.info("%sCluster at (%d,%d): tier-1 recovery '%s' -> {%s}", tag, cx, cy, text, loose)
            return matches, attempts
        logger.info("%sCluster at (%d,%d): rejected tier-1 recovery {%s}.", tag, cx, cy, loose)

    cluster_area = sum(int(c.get("area", 0)) for c in cluster)
    cluster_fill = cluster_area / float(max(cw * ch, 1))
    tier2_shape_ok = not (cw >= 15 and ch >= 15 and cluster_fill <= 0.12)
    if not tier2_shape_ok:
        logger.info("%sCluster at (%d,%d): skipping tier-2 — shape %dx%d (fill %.2f) looks like a line/arrow.",
                    tag, cx, cy, cw, ch, cluster_fill)
    elif len(cluster) != 1:
        logger.info("%sCluster at (%d,%d): skipping tier-2 — %d component(s), not a single glyph.",
                    tag, cx, cy, len(cluster))
        tier2_shape_ok = False

    if tier2_shape_ok:
        bare_by_psm: Dict[int, str] = {}
        for psm, text in attempts:
            bare = _extract_key_bare(psm, text)
            if bare is not None:
                bare_by_psm[psm] = bare.upper()

        agreed = (
            all(psm in bare_by_psm for psm in _TIER2_TRUSTED_PSMS)
            and len(set(bare_by_psm[psm] for psm in _TIER2_TRUSTED_PSMS)) == 1
        )

        if agreed:
            bare = bare_by_psm[_TIER2_TRUSTED_PSMS[0]]
            if _is_allowed_key(bare, allowed_keys):
                matches.append(PlaceholderMatch("{" + bare + "}", bare, cx, cy, cw, ch, color, source="tier2"))
                logger.info("%sCluster at (%d,%d): tier-2 bare recovery, psm%s agree -> {%s}",
                            tag, cx, cy, _TIER2_TRUSTED_PSMS, bare)
                return matches, attempts
            logger.info("%sCluster at (%d,%d): rejected tier-2 recovery {%s}.", tag, cx, cy, bare)
        elif bare_by_psm:
            logger.info("%sCluster at (%d,%d): tier-2 inconsistent across psm modes (%s) — discarding.",
                        tag, cx, cy, bare_by_psm)

    return matches, attempts


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def detect_placeholders(
    image: np.ndarray,
    template_key: Optional[str] = None,
    output_mapping: Optional[Dict[str, object]] = None,
) -> List[PlaceholderMatch]:
    """Detect {KEY} placeholders in a rendered template image, using and
    updating the persistent per-template learning cache."""
    tk = template_key or _template_key_for_image(image)
    allowed_keys, expected_counts = _normalize_output_mapping(output_mapping)

    if allowed_keys is not None:
        logger.info("OCR constrained to %d placeholder key(s): %s", len(allowed_keys), ", ".join(sorted(allowed_keys)))
        if expected_counts:
            logger.info("Expected placeholder counts: %s", expected_counts)

    cache = _load_json(_cache_path(tk))
    review = _load_json(_review_path(tk))
    cache_dirty = review_dirty = False

    labels, keep_mask, components = _connected_components(image)

    graphic_components = [c for c in components if _is_obvious_graphic_component(c)]
    remaining = [c for c in components if not _is_obvious_graphic_component(c)]

    graphic_ids = {c["label_id"] for c in graphic_components}
    satellite_ids = _mark_arrow_satellites(components, graphic_ids)
    if satellite_ids:
        graphic_components += [c for c in remaining if c["label_id"] in satellite_ids]
        remaining = [c for c in remaining if c["label_id"] not in satellite_ids]

    components = remaining
    if graphic_components:
        logger.info("Filtered %d obvious graphic component(s) (including %d arrow-satellite).",
                    len(graphic_components), len(satellite_ids))

    if _DEBUG:
        debug_mask = np.full_like(image, 255)
        debug_mask[keep_mask] = (0, 0, 0)
        _save_canvas(Image.fromarray(cv2.cvtColor(debug_mask, cv2.COLOR_BGR2RGB)), "generated/ocr_debug.png")

    clusters = _filter_clusters(_cluster_components(components), image.shape)
    logger.info("Formed %d candidate cluster(s) from %d component(s).", len(clusters), len(components))

    matches: List[PlaceholderMatch] = []
    cache_hits = 0

    def resolve(cx, cy, cw, ch, color, key, allow_overwrite_manual=False):
        nonlocal cache_dirty, review_dirty
        sig = _cluster_signature(cx, cy, cw, ch, color)
        if not allow_overwrite_manual and cache.get(sig, {}).get("source") == "manual":
            return
        cache[sig] = {"key": key, "source": "ocr_auto", "hits": 1}
        cache_dirty = True
        if sig in review:
            del review[sig]
            review_dirty = True

    for idx, cluster in enumerate(clusters):
        cx, cy, cw, ch = _cluster_bbox(cluster)
        color = _cluster_color(cluster)
        sig = _cluster_signature(cx, cy, cw, ch, color)

        cached = cache.get(sig)
        if cached:
            cached_key = str(cached.get("key", "")).upper()
            if not _is_allowed_key(cached_key, allowed_keys):
                logger.info("Ignoring cached key {%s} at (%d,%d): not in output mappings.", cached_key, cx, cy)
                cached = None
            else:
                cached["hits"] = cached.get("hits", 0) + 1
                cache_dirty = True
                matches.append(PlaceholderMatch("{" + cached_key + "}", cached_key, cx, cy, cw, ch, color, source="cache"))
                cache_hits += 1
                continue

        cluster_matches, attempts = _ocr_cluster(labels, cluster, idx, allowed_keys=allowed_keys)
        if cluster_matches:
            matches.extend(cluster_matches)
            if len(cluster_matches) == 1:
                resolve(cx, cy, cw, ch, color, cluster_matches[0].key)
            continue

        subclusters = _resplit_cluster_by_rows(cluster)
        if len(subclusters) > 1:
            logger.info("Cluster at (%d,%d) %dx%d: row re-split into %d sub-cluster(s).", cx, cy, cw, ch, len(subclusters))
            resplit_matches, resolved_n = [], 0
            for si, sub in enumerate(subclusters):
                sub_matches, _ = _ocr_cluster(labels, sub, idx, tag=f"[resplit {si}] ", allowed_keys=allowed_keys)
                if sub_matches:
                    resolved_n += 1
                    resplit_matches.extend(sub_matches)
                    if len(sub_matches) == 1:
                        sx, sy, sw, sh = _cluster_bbox(sub)
                        resolve(sx, sy, sw, sh, _cluster_color(sub), sub_matches[0].key)
            if resplit_matches:
                matches.extend(resplit_matches)
                if resolved_n < len(subclusters):
                    logger.warning("Cluster at (%d,%d): resplit recovered %d/%d.", cx, cy, resolved_n, len(subclusters))
                continue

        attempt_summary = ", ".join(f"psm{p}='{t}'" for p, t in attempts)
        logger.warning("Cluster at (%d,%d) %dx%d: no match (%s) — queued for review (template %s).",
                       cx, cy, cw, ch, attempt_summary, tk)
        canvas_path = _save_canvas(_render_cluster_canvas(labels, cluster)[0],
                                    os.path.join(_CACHE_DIR, _safe_filename(tk), "review_canvases", f"{sig}.png"))
        review[sig] = {"x": cx, "y": cy, "w": cw, "h": ch, "color": list(color),
                       "ocr_attempts": attempt_summary, "canvas_path": canvas_path, "last_seen": time.time()}
        review_dirty = True

    matches = _validate_counts(matches, expected_counts)

    if cache_dirty:
        _save_json(_cache_path(tk), cache)
    if review_dirty:
        _save_json(_review_path(tk), review)

    logger.info("OCR found %d placeholder(s) (%d from cache, %d needing review under %s).",
               len(matches), cache_hits, len(review), os.path.join(_CACHE_DIR, _safe_filename(tk)))
    return matches
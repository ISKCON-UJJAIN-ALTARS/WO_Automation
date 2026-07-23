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

# Detection / clustering tuning
_SAT_THRESHOLD, _VAL_MIN = 50, 30
_OPEN_KERNEL_SIZE, _CLOSE_KERNEL_SIZE = 2, 3
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

_DEBUG_DIR = "generated/ocr_debug_clusters"
_CACHE_DIR = "generated/ocr_cache"
_SIG_BUCKET_PX, _SIG_BUCKET_COLOR = 8, 16


@dataclass
class PlaceholderMatch:
    token: str
    key: str
    x: int
    y: int
    w: int
    h: int
    color: Tuple[int, int, int]


# --------------------------------------------------------------------------
# Learning cache: same template renders repeatedly with identical
# placeholder geometry/color, so once a cluster is resolved (by OCR or a
# manual apply_correction call) it's cached by a position+size+color
# signature and never needs OCR again. Unresolved clusters go to a review
# queue with a saved canvas instead of just a log line.
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

def _colored_mask(image: np.ndarray) -> np.ndarray:
    h, s, v = cv2.split(cv2.cvtColor(image, cv2.COLOR_BGR2HSV))
    return (s > _SAT_THRESHOLD) & (v > _VAL_MIN)


def _connected_components(image: np.ndarray) -> Tuple[np.ndarray, np.ndarray, List[dict]]:
    mask = _colored_mask(image).astype(np.uint8) * 255
    opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((_OPEN_KERNEL_SIZE,) * 2, np.uint8))
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(opened, connectivity=8)
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
# Rendering + OCR
# --------------------------------------------------------------------------

def _normalize_output_mapping(
    output_mapping: Optional[Dict[str, object]]
) -> Tuple[Optional[Set[str]], Dict[str, int]]:
    """Normalize the output mapping supplied by the generation workflow.

    The OCR service should only accept placeholder keys that are actually
    present in the current output mapping. Values are treated as expected
    occurrence counts when they can be converted to non-negative integers.
    """
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
    """Return True when key is valid for this generation request.

    If no output mapping is supplied, preserve backwards compatibility and
    allow all syntactically valid keys.
    """
    normalized = key.strip().upper()
    return allowed_keys is None or normalized in allowed_keys


def _component_features(component: dict) -> Tuple[float, float]:
    """Return aspect ratio and fill ratio for a connected component."""
    w = max(int(component["w"]), 1)
    h = max(int(component["h"]), 1)
    area = max(int(component["area"]), 0)
    aspect_ratio = max(w, h) / max(min(w, h), 1)
    fill_ratio = area / float(w * h)
    return aspect_ratio, fill_ratio


def _is_obvious_graphic_component(component: dict) -> bool:
    """Reject components that are overwhelmingly likely to be drawing graphics.

    Templates contain blue dimension arrows, long measurement lines and filled
    blue rectangles in addition to blue placeholder text. These components
    should not enter the OCR clustering pipeline.

    The thresholds are intentionally conservative: only very obvious graphics
    are rejected here. Text-like components remain available for OCR.
    """
    aspect_ratio, fill_ratio = _component_features(component)
    w = int(component["w"])
    h = int(component["h"])

    # Long, thin strokes are normally dimension lines/arrows.
    if aspect_ratio >= 12.0:
        return True

    # Large solid regions are normally filled drawing shapes rather than text.
    if w >= 12 and h >= 8 and fill_ratio >= 0.70:
        return True

    return False


def _validate_matches(
    matches: List["PlaceholderMatch"],
    allowed_keys: Optional[Set[str]],
    tag: str = "",
) -> List["PlaceholderMatch"]:
    """Keep only matches whose keys are valid for this generation request."""
    valid = []

    for match in matches:
        key = str(match.key or "").strip().upper()
        if not _is_allowed_key(key, allowed_keys):
            logger.info(
                "%sRejected OCR candidate {%s}: key is not present in current "
                "output mappings.",
                tag,
                key,
            )
            continue

        match.key = key
        match.token = "{" + key + "}"
        valid.append(match)

    return valid



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
    """Try psm 7 (line) -> 8 (word) -> 6 (block) -> 10 (single char),
    stopping at the first clean single {KEY} match. Returns every attempt
    made so callers can reuse them for recovery/logging without more
    Tesseract subprocess calls."""
    attempts = []
    for psm in (7, 8, 6, 10):
        text = _ocr_text(pil_img, psm)
        attempts.append((psm, text))
        if len(list(_PLACEHOLDER_RE.finditer(text))) == 1:
            return text, psm, attempts
    return attempts[0][1], attempts[0][0], attempts


def _extract_key_loose(raw_text: str) -> Optional[str]:
    """Tier 1: braces got garbled (e.g. '{A{') but inner text is clean.
    Requires a brace character present as evidence this was a placeholder."""
    if "{" not in raw_text and "}" not in raw_text:
        return None
    stripped = raw_text.replace("{", "").replace("}", "").strip()
    return stripped if _LOOSE_KEY_RE.match(stripped) else None


def _extract_key_bare(psm: int, text: str) -> Optional[str]:
    """Tier 2: no brace evidence at all — only for tiny clusters whose
    brace glyphs likely never survived the color threshold. Only trusts
    single-word/single-char psm modes and rejects underscore-only noise."""
    if psm not in _TIER2_TRUSTED_PSMS:
        return None
    stripped = text.strip()
    if not stripped or set(stripped) == {"_"}:
        return None
    return stripped if _LOOSE_KEY_RE.match(stripped) and len(stripped) <= 4 else None


def _char_boxes(pil_crop: Image.Image) -> List[Tuple[str, int, int, int, int]]:
    """Per-character boxes via sparse-text mode (psm 11, no single-line
    assumption) so overlapping/stacked placeholders can be separated."""
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
    """Row-aware split for a cluster containing >1 (or misread) {KEY}s —
    e.g. two same-colored, stacked, or overlapping placeholders."""
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
    """Full pipeline for one cluster: flat OCR -> row-aware split ->
    brace-garbled recovery -> no-brace recovery."""
    pil_img, x0, y0 = _render_cluster_canvas(labels, cluster)
    if _DEBUG:
        _save_canvas(pil_img, os.path.join(_DEBUG_DIR, f"cluster_{idx:02d}_{x0}_{y0}{'_' + tag if tag else ''}.png"))

    raw_text, psm_used, attempts = _ocr_with_fallbacks(pil_img)
    found = list(_PLACEHOLDER_RE.finditer(raw_text))
    cx, cy, cw, ch = _cluster_bbox(cluster)
    color = _cluster_color(cluster)
    matches: List[PlaceholderMatch] = []

    if len(found) == 1:
        key = found[0].group(1).upper()
        if not _is_allowed_key(key, allowed_keys):
            logger.info(
                "%sCluster at (%d,%d): rejected OCR key {%s}; "
                "not present in current output mappings.",
                tag, cx, cy, key
            )
            return matches, attempts

        matches.append(PlaceholderMatch("{" + key + "}", key, cx, cy, cw, ch, color))
        return matches, attempts

    split = _split_cluster_into_tokens(pil_img, x0, y0, _OCR_SCALE)
    if split:
        for key, sx, sy, sw, sh in split:
            key = key.upper()
            if not _is_allowed_key(key, allowed_keys):
                logger.info(
                    "%sCluster at (%d,%d): rejected split OCR key {%s}; "
                    "not present in current output mappings.",
                    tag, cx, cy, key
                )
                continue

            matches.append(
                PlaceholderMatch(
                    "{" + key + "}", key, sx, sy, sw, sh, color
                )
            )

        if matches:
            logger.info(
                "%sCluster at (%d,%d): split into %d valid token(s) (raw='%s')",
                tag, cx, cy, len(matches), raw_text
            )
            return matches, attempts

    if len(found) > 1:
        for m in found:
            key = m.group(1).upper()
            if not _is_allowed_key(key, allowed_keys):
                logger.info(
                    "%sCluster at (%d,%d): rejected merged OCR key {%s}; "
                    "not present in current output mappings.",
                    tag, cx, cy, key
                )
                continue

            matches.append(
                PlaceholderMatch(
                    "{" + key + "}", key, cx, cy, cw, ch, color
                )
            )

        if matches:
            logger.warning(
                "%sCluster at (%d,%d): couldn't split '%s', kept valid matches.",
                tag, cx, cy, raw_text
            )
            return matches, attempts

    for _, text in attempts:
        loose = _extract_key_loose(text)
        if loose is None:
            continue
        loose = loose.upper()
        if _is_allowed_key(loose, allowed_keys):
            matches.append(
                PlaceholderMatch(
                    "{" + loose + "}", loose, cx, cy, cw, ch, color
                )
            )
            logger.info(
                "%sCluster at (%d,%d): tier-1 recovery '%s' -> {%s}",
                tag, cx, cy, text, loose
            )
            return matches, attempts

        logger.info(
            "%sCluster at (%d,%d): rejected tier-1 recovery {%s}; "
            "not present in current output mappings.",
            tag, cx, cy, loose
        )

    # IMPORTANT: Do not use bare OCR as an automatic placeholder detector.
    # Without brace evidence, arrows, dimension labels, line fragments and
    # other graphics frequently become false positives such as {1}, {T},
    # {HIM}, {CE}, {8} and {J}. Such candidates are sent to review instead.
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
    updating the persistent per-template learning cache. template_key
    defaults to a hash of the image bytes, so repeat renders of the same
    template automatically reuse everything already learned about it."""
    tk = template_key or _template_key_for_image(image)
    allowed_keys, expected_counts = _normalize_output_mapping(output_mapping)

    if allowed_keys is not None:
        logger.info(
            "OCR constrained to %d placeholder key(s) from output mappings: %s",
            len(allowed_keys),
            ", ".join(sorted(allowed_keys)),
        )
        if expected_counts:
            logger.info(
                "Expected placeholder counts: %s",
                expected_counts,
            )

    cache = _load_json(_cache_path(tk))
    review = _load_json(_review_path(tk))
    cache_dirty = review_dirty = False

    labels, keep_mask, components = _connected_components(image)

    # Keep the original label image intact, but exclude obvious drawing
    # graphics from OCR candidate clustering.
    graphic_components = [c for c in components if _is_obvious_graphic_component(c)]
    components = [c for c in components if not _is_obvious_graphic_component(c)]

    if graphic_components:
        logger.info(
            "Filtered %d obvious graphic component(s) before OCR clustering.",
            len(graphic_components),
        )

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

            # Never reuse a cached result that is impossible for the current
            # output mapping. This also protects against stale/wrong OCR cache
            # entries from an earlier version of the detector.
            if not _is_allowed_key(cached_key, allowed_keys):
                logger.info(
                    "Ignoring cached key {%s} at (%d,%d): not present in "
                    "current output mappings.",
                    cached_key, cx, cy
                )
                cached = None
            else:
                cached["hits"] = cached.get("hits", 0) + 1
                cache_dirty = True
                matches.append(
                    PlaceholderMatch(
                        "{" + cached_key + "}",
                        cached_key,
                        cx, cy, cw, ch, color
                    )
                )
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
            logger.info("Cluster at (%d,%d) %dx%d: row re-split into %d sub-cluster(s).",
                        cx, cy, cw, ch, len(subclusters))
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

    if cache_dirty:
        _save_json(_cache_path(tk), cache)
    if review_dirty:
        _save_json(_review_path(tk), review)

    logger.info("OCR found %d placeholder(s) (%d from cache, %d needing review under %s).",
               len(matches), cache_hits, len(review), os.path.join(_CACHE_DIR, _safe_filename(tk)))
    return matches
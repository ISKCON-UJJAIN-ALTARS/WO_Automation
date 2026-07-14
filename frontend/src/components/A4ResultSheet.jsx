import { useState } from "react";
import { downloadUrl, imageUrl } from "../api";

// Must match .a4-sheet's own CSS: total size and internal padding/gap.
// Kept in sync here so we can compute exact mm positions in JS — every
// image is placed with an absolute { left, top, width, height } instead of
// relying on CSS Flexbox/Grid to infer it, because Chrome's print-to-PDF
// pipeline wasn't reliably resolving percentage/1fr sizes through nested
// layouts, letting images overflow their slot and get clipped.
const SHEET_WIDTH_MM = 210;
const SHEET_HEIGHT_MM = 255;
const SHEET_PADDING_MM = 10; // each side
const GAP_MM = 5;
const USABLE_WIDTH_MM = SHEET_WIDTH_MM - SHEET_PADDING_MM * 2;
const USABLE_HEIGHT_MM = SHEET_HEIGHT_MM - SHEET_PADDING_MM * 2;

// Used only until an image's real aspect ratio is known (briefly, while it
// loads), so the layout doesn't jump too wildly once the real ratio lands.
const FALLBACK_ASPECT_RATIO = 1.5;

/**
 * Split `items` (in their given order) into `numRows` contiguous, roughly
 * equal-sized groups. Kept simple/deterministic rather than reordering by
 * ratio, so the on-screen legend order still matches what's on the page.
 */
function splitIntoRows(items, numRows) {
  const base = Math.floor(items.length / numRows);
  let extra = items.length % numRows;
  const rows = [];
  let idx = 0;
  for (let r = 0; r < numRows; r++) {
    const count = base + (extra > 0 ? 1 : 0);
    if (extra > 0) extra -= 1;
    rows.push(items.slice(idx, idx + count));
    idx += count;
  }
  return rows;
}

/**
 * "Justified row" packing — the same idea Google Photos / Flickr-style
 * gallery layouts use: every row's shared height is whatever makes that
 * row's images (each keeping its own real aspect ratio) collectively span
 * the FULL usable width with no gaps. This wastes far less space than
 * fixed-width columns, since a column-based masonry grid can leave a big
 * uneven gap wherever one column's stack falls short of another's — a
 * justified row never has that problem, because it's solved for exactly
 * fitting the width every time.
 */
function packRows(items, numRows) {
  const rows = splitIntoRows(items, numRows);
  let y = 0;
  const rowLayouts = rows.map((row) => {
    const gapTotal = GAP_MM * (row.length - 1);
    const sumRatios = row.reduce((s, it) => s + it.ratio, 0);
    const rowHeight = (USABLE_WIDTH_MM - gapTotal) / sumRatios;
    let x = 0;
    const placements = row.map((item) => {
      const width = rowHeight * item.ratio;
      const placement = { ...item, x, y, width, height: rowHeight };
      x += width + GAP_MM;
      return placement;
    });
    y += rowHeight + GAP_MM;
    return placements;
  });
  const totalHeight = y - GAP_MM; // no trailing gap after the last row
  return { placements: rowLayouts.flat(), totalHeight };
}

/**
 * Try every possible row count (1 row, 2 rows, ... up to one row per item)
 * and keep whichever fills the page most completely. Preference order:
 * (1) avoid shrinking below natural size if at all possible — a layout
 * that needs shrinking produces smaller, less legible drawings even if it
 * technically uses 100% of the page; (2) among options that don't need
 * shrinking, prefer whichever leaves the least blank space at the bottom.
 */
function findBestLayout(items) {
  let best = null;
  for (let numRows = 1; numRows <= items.length; numRows++) {
    const { placements, totalHeight } = packRows(items, numRows);
    const scale = totalHeight > USABLE_HEIGHT_MM ? USABLE_HEIGHT_MM / totalHeight : 1;
    const fillRatio = Math.min(totalHeight * scale, USABLE_HEIGHT_MM) / USABLE_HEIGHT_MM;

    if (!best || scale > best.scale || (scale === best.scale && fillRatio > best.fillRatio)) {
      best = { numRows, placements, totalHeight, scale, fillRatio };
    }
  }
  return best;
}

/**
 * Lays out every successfully generated drawing (one per selected
 * component, e.g. Ceiling·3-Dome + Ceiling·4-Dome + Base-Box·Top) onto a
 * single, fixed-size A4 page as a justified-row grid — images only, no
 * values table. Row count/grouping is chosen automatically per generation
 * to pack the page as tightly as possible without shrinking below natural
 * size; every image keeps its own true aspect ratio (read from the browser
 * via naturalWidth/naturalHeight). If the packed layout would still
 * overflow one page even at 1 row per item, the WHOLE grid is scaled down
 * by one shared factor (never per-image) so nothing gets clipped and no
 * drawing is distorted relative to the others.
 *
 * `window.print()` + the `@media print` rules in index.css hide everything
 * else on screen, so "Print" effectively becomes "Save as PDF" in the
 * browser's print dialog.
 */
export default function A4ResultSheet({ apiBase, results }) {
  const successful = (results || []).filter((r) => r.success);
  const failed = (results || []).filter((r) => !r.success);

  // templateKey -> naturalWidth/naturalHeight aspect ratio, filled in as
  // each <img> finishes loading in the browser.
  const [aspectRatios, setAspectRatios] = useState({});

  if (successful.length === 0) return null;

  const items = successful.map((r) => ({
    templateKey: r.templateKey,
    label: r.label,
    ratio: aspectRatios[r.templateKey] || FALLBACK_ASPECT_RATIO,
  }));

  const layout = findBestLayout(items);
  // placements are in the same order as `items`/`successful`, since
  // splitIntoRows keeps items in order and .flat() preserves row order.
  const placementByKey = Object.fromEntries(layout.placements.map((p) => [p.templateKey, p]));

  function handleImageLoad(templateKey, e) {
    const { naturalWidth, naturalHeight } = e.currentTarget;
    if (!naturalWidth || !naturalHeight) return;
    const ratio = naturalWidth / naturalHeight;
    setAspectRatios((prev) =>
      prev[templateKey] === ratio ? prev : { ...prev, [templateKey]: ratio }
    );
  }

  function handlePrintClick() {
    try {
      window.print();
    } catch (err) {
      console.error("[A4ResultSheet] window.print() threw:", err);
      alert(`Could not open the print dialog: ${err.message}`);
    }
  }

  return (
    <>
      {/* a4-no-print: this action bar must never appear on the printed
          page/PDF itself, only on screen. */}
      <div className="a4-actions a4-no-print">
        <button type="button" className="submit-btn" onClick={handlePrintClick}>
          Print / Save as PDF (A4)
        </button>
        <span className="a4-actions-hint">
          {successful.length} drawing{successful.length > 1 ? "s" : ""} on one A4 page ·{" "}
          {layout.numRows} row{layout.numRows > 1 ? "s" : ""} ·{" "}
          {Math.round(layout.fillRatio * 100)}% of the page used
          {failed.length > 0 ? ` · ${failed.length} failed (see above)` : ""}
        </span>
      </div>

      {/* On-screen-only legend, since individual captions would overlap in
          a tightly packed justified grid. */}
      <ol className="a4-legend a4-no-print">
        {successful.map((r) => (
          <li key={r.templateKey}>{r.label}</li>
        ))}
      </ol>

      <div className="a4-sheet" id="a4-print-sheet">
        {successful.map((r) => {
          const imgUrl = imageUrl(apiBase, r.data.image_path);
          const p = placementByKey[r.templateKey];
          const style = {
            left: `${p.x * layout.scale}mm`,
            top: `${p.y * layout.scale}mm`,
            width: `${p.width * layout.scale}mm`,
            height: `${p.height * layout.scale}mm`,
          };
          return (
            <div className="a4-item" key={r.templateKey} style={style}>
              <img
                src={imgUrl}
                alt={`Generated drawing: ${r.label}`}
                onLoad={(e) => handleImageLoad(r.templateKey, e)}
                onError={(e) => {
                  e.currentTarget.outerHTML = `<div class="image-load-error">Image returned by the API but could not load from ${imgUrl}.</div>`;
                }}
              />
            </div>
          );
        })}
      </div>

      <div className="a4-below-actions a4-no-print">
        {successful.map((r) => {
          const filename = r.data.image_path?.split("/").pop();
          const dlUrl = downloadUrl(apiBase, filename);
          const imgUrl = imageUrl(apiBase, r.data.image_path);
          return (
            <div className="actions-row" key={r.templateKey}>
              <a href={dlUrl} target="_blank" rel="noopener noreferrer">
                Download {r.label} PNG
              </a>
              <button type="button" onClick={() => window.open(imgUrl, "_blank")}>
                Open Raw Image
              </button>
            </div>
          );
        })}
      </div>
    </>
  );
}

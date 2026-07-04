import { downloadUrl, imageUrl } from "../api";

/**
 * Lays out every successfully generated drawing (one per selected variant,
 * e.g. Ceiling + Base Box) onto a single, fixed-height A4 page — images
 * only, no values table. Each drawing gets an equal vertical slot and
 * scales down (preserving aspect ratio) to fit inside it, so N drawings
 * always share ONE page instead of spilling onto a second one.
 *
 * `window.print()` + the `@media print` rules in index.css hide everything
 * else on screen, so "Print" effectively becomes "Save as PDF" in the
 * browser's print dialog.
 */
export default function A4ResultSheet({ apiBase, results }) {
  const successful = (results || []).filter((r) => r.success);
  const failed = (results || []).filter((r) => !r.success);

  if (successful.length === 0) return null;

  function handlePrintClick() {
    console.log("[A4ResultSheet] Print button clicked, calling window.print()");
    try {
      window.print();
    } catch (err) {
      console.error("[A4ResultSheet] window.print() threw:", err);
      alert(`Could not open the print dialog: ${err.message}`);
    }
  }

  return (
    <>
      <div className="a4-actions">
        <button type="button" className="submit-btn" onClick={handlePrintClick}>
          Print / Save as PDF (A4)
        </button>
        <span className="a4-actions-hint">
          {successful.length} drawing{successful.length > 1 ? "s" : ""} on one A4 page
          {failed.length > 0 ? ` · ${failed.length} failed (see above)` : ""}
        </span>
      </div>

      <div className="a4-sheet" id="a4-print-sheet">
        {successful.map((r) => {
          const imgUrl = imageUrl(apiBase, r.data.image_path);
          return (
            <div className="a4-block" key={r.templateKey}>
              {/* Label shown on screen for reference only — not printed, so the
                  A4 page contains only the drawings themselves. */}
              <div className="a4-block-title a4-no-print">{r.label}</div>
              <div className="a4-drawing-frame">
                <img
                  src={imgUrl}
                  alt={`Generated drawing: ${r.label}`}
                  onError={(e) => {
                    e.currentTarget.outerHTML = `<div class="image-load-error">Image returned by the API but could not load from ${imgUrl}.</div>`;
                  }}
                />
              </div>
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

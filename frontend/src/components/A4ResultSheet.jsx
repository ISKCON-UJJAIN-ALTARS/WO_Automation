import { useState } from "react";
import { downloadUrl, imageUrl } from "../api";

/**
 * Lays out every successfully generated drawing (one per selected variant,
 * e.g. Ceiling + Base Box) onto a single A4-sized sheet, stacked so it prints
 * as one page (or overflows cleanly onto a second page if there isn't room).
 * `window.print()` + the `@media print` rules in index.css hide everything
 * else on screen, so "Print" effectively becomes "Save as PDF" in the
 * browser's print dialog.
 */
export default function A4ResultSheet({ apiBase, results }) {
  const [copied, setCopied] = useState(null);

  const successful = (results || []).filter((r) => r.success);
  const failed = (results || []).filter((r) => !r.success);

  if (successful.length === 0) return null;

  function copyJson(templateKey, values) {
    navigator.clipboard.writeText(JSON.stringify(values, null, 2));
    setCopied(templateKey);
    setTimeout(() => setCopied(null), 1200);
  }

  return (
    <>
      <div className="a4-actions">
        <button
          type="button"
          className="submit-btn"
          onClick={() => {
            console.log("[A4ResultSheet] Print button clicked, calling window.print()");
            try {
              window.print();
            } catch (err) {
              console.error("[A4ResultSheet] window.print() threw:", err);
              alert(`Could not open the print dialog: ${err.message}`);
            }
          }}
        >
          Print / Save as PDF (A4)
        </button>
        <span className="a4-actions-hint">
          {successful.length} drawing{successful.length > 1 ? "s" : ""} on one sheet
          {failed.length > 0 ? ` · ${failed.length} failed (see above)` : ""}
        </span>
      </div>

      <div className="a4-sheet" id="a4-print-sheet">
        {successful.map((r) => {
          const imgUrl = imageUrl(apiBase, r.data.image_path);
          const filename = r.data.image_path?.split("/").pop();
          const dlUrl = downloadUrl(apiBase, filename);
          const entries = Object.entries(r.data.values || {});

          return (
            <div className="a4-block" key={r.templateKey}>
              <div className="a4-block-title">{r.label}</div>

              <div className="drawing-frame a4-drawing-frame">
                <img
                  src={imgUrl}
                  alt={`Generated drawing: ${r.label}`}
                  onError={(e) => {
                    e.currentTarget.outerHTML = `<div class="image-load-error">Image returned by the API but could not load from ${imgUrl}.</div>`;
                  }}
                />
              </div>

              <div className="values-head a4-no-print">
                <h3>Calculated Values</h3>
                <button type="button" className="copy-btn" onClick={() => copyJson(r.templateKey, r.data.values)}>
                  {copied === r.templateKey ? "Copied" : "Copy JSON"}
                </button>
              </div>

              <table className="values-table">
                <tbody>
                  {entries.map(([k, v]) => (
                    <tr key={k}>
                      <td className="k">{k}</td>
                      <td className="v">{v === null || v === undefined ? "—" : String(v)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="actions-row a4-no-print">
                <a href={dlUrl} target="_blank" rel="noopener noreferrer">
                  Download PNG
                </a>
                <button type="button" onClick={() => window.open(imgUrl, "_blank")}>Open Raw Image</button>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
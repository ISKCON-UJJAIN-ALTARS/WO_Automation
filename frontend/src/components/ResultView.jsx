import { useState } from "react";
import { downloadUrl, imageUrl } from "../api";

/** Renders the generated drawing image, calculated values table, and actions. */
export default function ResultView({ apiBase, data }) {
  const [copied, setCopied] = useState(false);

  const imgUrl = imageUrl(apiBase, data.image_path);
  const filename = data.image_path?.split("/").pop();
  const dlUrl = downloadUrl(apiBase, filename);
  const entries = Object.entries(data.values || {});

  function copyJson() {
    navigator.clipboard.writeText(JSON.stringify(data.values, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  }

  return (
    <>
      <div className="drawing-frame">
        <img
          src={imgUrl}
          alt="Generated work order drawing"
          onError={(e) => {
            e.currentTarget.outerHTML = `<div class="image-load-error">Image returned by the API but could not load from ${imgUrl}. Check that /generated is mounted and reachable from this origin.</div>`;
          }}
        />
      </div>

      <div className="values-head">
        <h3>Calculated Values</h3>
        <button className="copy-btn" onClick={copyJson}>
          {copied ? "Copied" : "Copy JSON"}
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

      <div className="actions-row">
        <a href={dlUrl} target="_blank" rel="noopener noreferrer">
          Download PNG
        </a>
        <button onClick={() => window.open(imgUrl, "_blank")}>Open Raw Image</button>
      </div>
    </>
  );
}

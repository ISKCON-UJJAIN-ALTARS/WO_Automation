/**
 * Thin client around the Divine Sky FastAPI backend.
 * Every function here corresponds to one real endpoint documented in
 * backend/app/routes/templates.py — nothing here invents API shape.
 */

function normalizeBase(base) {
  return base.trim().replace(/\/$/, "");
}

/** GET /templates — used as a lightweight health check too. */
export async function fetchTemplates(apiBase) {
  const res = await fetch(`${normalizeBase(apiBase)}/templates`, { method: "GET" });
  if (!res.ok) {
    throw new Error(`responded with ${res.status}`);
  }
  return res.json();
}

/**
 * POST /generate
 * @param {string} apiBase
 * @param {string} templateKey - e.g. "3dome_ceiling", "4dome_ceiling"
 * @param {Record<string, number>} inputs
 * @returns {Promise<{ image_path: string, values: Record<string, number|string> }>}
 */
export async function generateDrawing(apiBase, templateKey, inputs) {
  const res = await fetch(`${normalizeBase(apiBase)}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ template: templateKey, inputs }),
  });

  const data = await res.json().catch(() => null);

  if (!res.ok) {
    const detail = data?.detail || `Request failed with status ${res.status}`;
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }

  return data;
}

/** Builds the absolute URL for GET /generate/download?filename=... */
export function downloadUrl(apiBase, filename) {
  return `${normalizeBase(apiBase)}/generate/download?filename=${encodeURIComponent(filename)}`;
}

/** Builds the absolute URL for the static-mounted generated image itself. */
export function imageUrl(apiBase, imagePath) {
  return `${normalizeBase(apiBase)}${imagePath}`;
}

/**
 * Variant/category metadata for the wizard.
 *
 * IMPORTANT: `fields` (per variant) is no longer hardcoded here. It used to
 * duplicate the backend's field lists by hand, which drifted out of sync
 * (e.g. basebox variants incorrectly all shared the same 5 fields, and
 * "back" didn't match the backend's real key "back_side"). Now the field
 * lists come live from GET /templates, which returns each template's real
 * `input_fields` (key, label, unit, type, options) straight from
 * app/config/templates.json + field_catalog.json.
 *
 * CATEGORIES and the icon/label/sub/grouping metadata below are presentation
 * concerns the backend doesn't know about, so those stay here — but the
 * *fields* array on each variant is populated at runtime by
 * loadVariantsFromBackend(), not written by hand.
 */

import { fetchTemplates } from "./api";

export const CATEGORIES = [
  {
    key: "ceiling",
    label: "Ceiling",
    blurb: "Dome cutting sets for the ceiling box",
    icon: "ceiling",
  },
  {
    key: "basebox",
    label: "Base Box",
    blurb: "Base box cutting set",
    icon: "basebox",
  },
];

// Presentation metadata per template key: which category it belongs to,
// its label/sub/icon. The backend doesn't need to know any of this — it's
// purely how the wizard groups and displays templates it already knows about
// from /templates. If the backend adds a new template key, add one line
// here to place it in the UI; no field lists to maintain.
const VARIANT_META = {
  "3dome_ceiling": { category: "ceiling", label: "3 Dome", sub: "Ceiling Cutting", icon: "dome3" },
  "4dome_ceiling": { category: "ceiling", label: "4 Dome", sub: "Ceiling Cutting", icon: "dome4" },
  top:             { category: "basebox", label: "Top",     sub: "Base Box Cutting", icon: "box" },
  back_side:       { category: "basebox", label: "Back",    sub: "Base Box Cutting", icon: "box" },
  bottom:          { category: "basebox", label: "Bottom",  sub: "Base Box Cutting", icon: "box" },
  step_0:          { category: "basebox", label: "Step 0",  sub: "Base Box Cutting", icon: "box" },
  step_1:          { category: "basebox", label: "Step 1",  sub: "Base Box Cutting", icon: "box" },
  step_2:          { category: "basebox", label: "Step 2",  sub: "Base Box Cutting", icon: "box" },
  step_3:          { category: "basebox", label: "Step 3",  sub: "Base Box Cutting", icon: "box" },
};

/**
 * Fetches GET /templates (via api.js's fetchTemplates, so it shares the same
 * apiBase state the rest of the app uses — no separate env var) and returns
 * a VARIANTS object shaped exactly like the old hardcoded one:
 *   { [categoryKey]: [ { key, label, sub, icon, wired, fields }, ... ] }
 *
 * `fields` here is the real, per-template field list straight from the
 * backend (each item: { key, cell, label, unit, type, options }), so a
 * template that only needs 3 fields only gets 3 — no more copy-pasted
 * 5-field blocks that don't match reality. Every template /templates
 * returns is by definition already wired (it only lists templates that
 * exist in the backend's config), so `wired` is always true here.
 */
export async function loadVariantsFromBackend(apiBase) {
  const data = await fetchTemplates(apiBase); // { [templateKey]: { template_image, input_fields } }

  const variants = {};
  for (const [templateKey, cfg] of Object.entries(data)) {
    const meta = VARIANT_META[templateKey];
    if (!meta) {
      // Backend has a template the frontend doesn't know how to group/label
      // yet — surface it under a fallback bucket instead of silently
      // dropping it, so new backend templates are never invisible.
      console.warn(`No VARIANT_META entry for backend template "${templateKey}" — add one in config.js`);
      continue;
    }
    const variant = {
      key: templateKey,
      label: meta.label,
      sub: meta.sub,
      icon: meta.icon,
      wired: true, // if /templates returned it, the backend config exists
      fields: cfg.input_fields.map((f) => ({
        key: f.key,
        label: f.label,
        unit: f.unit,
        type: f.type || "number",
        options: f.options || null,
        integer: f.type === "select" && typeof f.options?.[0]?.value === "number" ? false : undefined,
      })),
    };
    if (!variants[meta.category]) variants[meta.category] = [];
    variants[meta.category].push(variant);
  }
  return variants;
}

export function findVariant(variants, categoryKey, variantKey) {
  if (!categoryKey) return null;
  return (variants[categoryKey] || []).find((v) => v.key === variantKey) || null;
}

export function findCategory(categoryKey) {
  return CATEGORIES.find((c) => c.key === categoryKey) || null;
}

/**
 * Merge the `fields` arrays of several chosen variants into one deduplicated
 * list, keyed by field `key`. Fields that appear in more than one variant
 * are asked only once on the combined form. Each merged field carries
 * `usedBy`, the list of variant keys that need it, so the UI can label
 * shared fields.
 */
export function mergeFields(variants) {
  const map = new Map();
  variants.forEach((variant) => {
    variant.fields.forEach((f) => {
      const existing = map.get(f.key);
      if (existing) {
        if (!existing.usedBy.includes(variant.key)) existing.usedBy.push(variant.key);
      } else {
        map.set(f.key, { ...f, usedBy: [variant.key] });
      }
    });
  });
  return Array.from(map.values());
}

/** Pull out just the fields a single variant needs from the shared/merged values object. */
export function buildVariantInputs(variant, sharedValues) {
  const inputs = {};
  variant.fields.forEach((f) => {
    inputs[f.key] = sharedValues[f.key];
  });
  return inputs;
}
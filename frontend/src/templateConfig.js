/**
 * Mirrors the backend's app/config/template_mappings.json and
 * app/schemas/request_models.py.
 *
 * "wired: true"  -> the template key exists in template_mappings.json on the
 *                   backend, so POST /generate will actually find a config
 *                   block, an Excel sheet, and a template image for it.
 * "wired: false" -> a Pydantic request schema exists for it, but there is no
 *                   matching entry in template_mappings.json yet. The form
 *                   still renders so the moment the backend config is added,
 *                   this UI works with zero changes — but submitting now
 *                   will hit a 404 from /generate.
 */

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

export const VARIANTS = {
  ceiling: [
    {
      key: "3dome_ceiling",
      label: "3 Dome",
      sub: "Ceiling Cutting",
      wired: true,
      icon: "dome3",
      fields: [
        { key: "altar_length", label: "Altar Length", unit: "in" },
        { key: "altar_depth", label: "Altar Depth", unit: "in" },
        { key: "pillar_width", label: "Pillar Width", unit: "in" },
        { key: "pillar_height", label: "Pillar Height", unit: "in" },
        { key: "arch_ratio", label: "Arch Ratio", unit: "ratio" },
      ],
    },
    {
      key: "4dome_ceiling",
      label: "4 Dome",
      sub: "Ceiling Cutting",
      wired: true,
      icon: "dome4",
      fields: [
        { key: "altar_length", label: "Altar Length", unit: "in" },
        { key: "altar_depth", label: "Altar Depth", unit: "in" },
        { key: "pillar_width", label: "Pillar Width", unit: "in" },
        { key: "pillar_height", label: "Pillar Height", unit: "in" },
        { key: "arch_ratio", label: "Arch Ratio", unit: "ratio" },
      ],
    },
  ],
  basebox: [
    {
      key: "top",
      label: "Top",
      sub: "Base Box Cutting",
      wired: true,
      icon: "box",
      fields: [
        { key: "altar_length", label: "Altar Length", unit: "in" },
        { key: "altar_depth", label: "Altar Depth", unit: "in" },
        { key: "altar_height", label: "Altar Height", unit: "in" },
        { key: "shelf_count", label: "Shelf Count", unit: "count", integer: true },
        { key: "door_width", label: "Door Width", unit: "in" },
      ],
    },
    {
      key: "back",
      label: "Back",
      sub: "Base Box Cutting",
      wired: true,
      icon: "box",
      fields: [
        { key: "altar_length", label: "Altar Length", unit: "in" },
        { key: "altar_depth", label: "Altar Depth", unit: "in" },
        { key: "altar_height", label: "Altar Height", unit: "in" },
        { key: "shelf_count", label: "Shelf Count", unit: "count", integer: true },
        { key: "door_width", label: "Door Width", unit: "in" },
      ],
    },
    {
      key: "bottom",
      label: "Bottom",
      sub: "Base Box Cutting",
      wired: true,
      icon: "box",
      fields: [
        { key: "altar_length", label: "Altar Length", unit: "in" },
        { key: "altar_depth", label: "Altar Depth", unit: "in" },
        { key: "altar_height", label: "Altar Height", unit: "in" },
        { key: "shelf_count", label: "Shelf Count", unit: "count", integer: true },
        { key: "door_width", label: "Door Width", unit: "in" },
      ],
    },
    {
      key: "step_0",
      label: "step 0",
      sub: "Base Box Cutting",
      wired: true,
      icon: "box",
      fields: [
        { key: "altar_length", label: "Altar Length", unit: "in" },
        { key: "altar_depth", label: "Altar Depth", unit: "in" },
        { key: "altar_height", label: "Altar Height", unit: "in" },
        { key: "shelf_count", label: "Shelf Count", unit: "count", integer: true },
        { key: "door_width", label: "Door Width", unit: "in" },
      ],
    },
    {
      key: "step_1",
      label: "step 1",
      sub: "Base Box Cutting",
      wired: true,
      icon: "box",
      fields: [
        { key: "altar_length", label: "Altar Length", unit: "in" },
        { key: "altar_depth", label: "Altar Depth", unit: "in" },
        { key: "altar_height", label: "Altar Height", unit: "in" },
        { key: "shelf_count", label: "Shelf Count", unit: "count", integer: true },
        { key: "door_width", label: "Door Width", unit: "in" },
      ],
    },
    {
      key: "step_2",
      label: "step 2",
      sub: "Base Box Cutting",
      wired: true,
      icon: "box",
      fields: [
        { key: "altar_length", label: "Altar Length", unit: "in" },
        { key: "altar_depth", label: "Altar Depth", unit: "in" },
        { key: "altar_height", label: "Altar Height", unit: "in" },
        { key: "shelf_count", label: "Shelf Count", unit: "count", integer: true },
        { key: "door_width", label: "Door Width", unit: "in" },
      ],
    },
    {
      key: "step_3",
      label: "step 3",
      sub: "Base Box Cutting",
      wired: true,
      icon: "box",
      fields: [
        { key: "altar_length", label: "Altar Length", unit: "in" },
        { key: "altar_depth", label: "Altar Depth", unit: "in" },
        { key: "altar_height", label: "Altar Height", unit: "in" },
        { key: "shelf_count", label: "Shelf Count", unit: "count", integer: true },
        { key: "door_width", label: "Door Width", unit: "in" },
      ],
    },
  ],
};

export function findVariant(categoryKey, variantKey) {
  if (!categoryKey) return null;
  return (VARIANTS[categoryKey] || []).find((v) => v.key === variantKey) || null;
}

export function findCategory(categoryKey) {
  return CATEGORIES.find((c) => c.key === categoryKey) || null;
}

/**
 * Merge the `fields` arrays of several chosen variants into one deduplicated
 * list, keyed by field `key`. Fields that appear in more than one variant
 * (e.g. "altar_length" in both a Ceiling and a Base Box variant) are asked
 * only once on the combined form. Each merged field carries `usedBy`, the
 * list of variant keys that need it, so the UI can label shared fields.
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
// src/utils/mergeFields.js
//
// SHARED-FIELD MERGING ENGINE
// ------------------------------------------------------------------
// Given a list of selected templates (e.g. "3dome_ceiling" + "base_box_standard"),
// produce:
//   - common: fields required by 2+ templates -> shown once under "Common Dimensions"
//   - perTemplate: map of templateId -> fields unique to that template
// This guarantees no field is ever rendered twice in the workspace,
// regardless of how many components/templates a user selects.

import { TEMPLATES, FIELD_LIBRARY } from '@/data/templates';

export function mergeTemplateFields(templateIds = []) {
  const templates = templateIds.map((id) => TEMPLATES[id]).filter(Boolean);

  const fieldUsageCount = {};
  templates.forEach((t) => {
    t.sharedFields.forEach((f) => {
      fieldUsageCount[f] = (fieldUsageCount[f] || 0) + 1;
    });
  });

  const common = Object.keys(fieldUsageCount)
    .filter((f) => fieldUsageCount[f] >= 1) // sharedFields are by definition shareable
    .filter((f) => templates.some((t) => t.sharedFields.includes(f)))
    .filter((f, idx, arr) => arr.indexOf(f) === idx)
    .map((key) => ({ key, ...FIELD_LIBRARY[key] }));

  const perTemplate = {};
  templates.forEach((t) => {
    perTemplate[t.id] = {
      template: t,
      fields: t.specificFields.map((key) => ({ key, ...FIELD_LIBRARY[key] })),
    };
  });

  return { common, perTemplate, templates };
}

export function buildDefaultValues(templateIds = []) {
  const { common, perTemplate } = mergeTemplateFields(templateIds);
  const values = {};
  common.forEach((f) => (values[f.key] = f.default));
  Object.values(perTemplate).forEach(({ fields }) =>
    fields.forEach((f) => (values[f.key] = f.default))
  );
  return values;
}

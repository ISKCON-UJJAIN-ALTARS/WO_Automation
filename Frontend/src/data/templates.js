// src/data/templates.js
//
// METADATA-DRIVEN ARCHITECTURE
// ------------------------------------------------------------------
// Every template (a "design") declares its own shared fields, specific
// fields, and the dimensions the backend will generate. Nothing about
// the workspace UI is hardcoded per-template — pages/Workspace.jsx and
// the shared-field merge engine (utils/mergeFields.js) read this file
// and render accordingly. Adding "base_box" or "pillars" later means
// adding an entry here — no component code changes required.

export const FIELD_LIBRARY = {
  altar_length: { label: 'Altar Length', unit: 'in', min: 12, max: 240, step: 0.5, default: 72 },
  altar_depth: { label: 'Altar Depth', unit: 'in', min: 8, max: 120, step: 0.5, default: 22 },
  pillar_width: { label: 'Pillar Width', unit: 'in', min: 1, max: 24, step: 0.25, default: 3.5 },
  pillar_height: { label: 'Pillar Height', unit: 'in', min: 6, max: 96, step: 0.5, default: 25 },
  arch_ratio: { label: 'Arch Ratio', unit: 'ratio', min: 1, max: 3, step: 0.001, default: 1.588 },
  dome_count: { label: 'Dome Count', unit: 'count', min: 1, max: 5, step: 1, default: 4 },
  shelf_count: { label: 'Shelf Count', unit: 'count', min: 0, max: 6, step: 1, default: 2 },
  door_width: { label: 'Door Width', unit: 'in', min: 6, max: 48, step: 0.5, default: 18 },
};

export const COMPONENTS = {
  ceiling: {
    id: 'ceiling',
    name: 'Ceiling',
    status: 'available',
    description: 'Dome ceiling structures with configurable arch geometry.',
  },
  base_box: {
    id: 'base_box',
    name: 'Base Box',
    status: 'available',
    description: 'Foundation housing with shelving and door configuration.',
  },
  pillars: { id: 'pillars', name: 'Pillars', status: 'coming_soon', description: 'Structural support columns.' },
  doors: { id: 'doors', name: 'Doors', status: 'coming_soon', description: 'Front-facing panel doors.' },
  drawers: { id: 'drawers', name: 'Drawers', status: 'coming_soon', description: 'Internal storage drawers.' },
  crown: { id: 'crown', name: 'Crown', status: 'coming_soon', description: 'Decorative crown moulding.' },
};

export const TEMPLATES = {
  '3dome_ceiling': {
    id: '3dome_ceiling',
    component: 'ceiling',
    name: '3 Dome Ceiling',
    description: 'Triple-arch dome ceiling with classic proportions, ideal for compact altars.',
    previewImage: '/assets/previews/3dome.svg',
    sharedFields: ['altar_length', 'altar_depth', 'pillar_width', 'pillar_height'],
    specificFields: ['arch_ratio'],
    generatedDimensions: ['TL', 'TSH', 'OW'],
  },
  '4dome_ceiling': {
    id: '4dome_ceiling',
    component: 'ceiling',
    name: '4 Dome Ceiling',
    description: 'Quad-arch dome ceiling for wide altar layouts with symmetrical massing.',
    previewImage: '/assets/previews/4dome.svg',
    sharedFields: ['altar_length', 'altar_depth', 'pillar_width', 'pillar_height'],
    specificFields: ['arch_ratio', 'dome_count'],
    generatedDimensions: ['TL', 'TSH', 'OW', 'INP'],
  },
  base_box_standard: {
    id: 'base_box_standard',
    component: 'base_box',
    name: 'Standard Base Box',
    description: 'Configurable shelving foundation with adjustable door width.',
    previewImage: '/assets/previews/basebox.svg',
    sharedFields: ['altar_length', 'altar_depth'],
    specificFields: ['shelf_count', 'door_width'],
    generatedDimensions: ['BSH', 'BSW', 'INW', 'INC'],
  },
};

// Human-readable engineering legend for every abbreviation the backend
// may return, independent of which templates use them.
export const DIMENSION_LEGEND = {
  TL: 'Top Length',
  TSH: 'Top Side Height',
  OW: 'Outer Width',
  INP: 'Inner Panel',
  BSH: 'Base Shelf Height',
  BSW: 'Base Shelf Width',
  INW: 'Inner Width',
  INC: 'Inner Clearance',
  RBL: 'Rear Brace Length',
  SL: 'Side Length',
  LP: 'Leg Projection',
  SW: 'Side Width',
  SH: 'Side Height',
  WP: 'Wall Projection',
  PH: 'Panel Height',
  PL: 'Panel Length',
};

export function getTemplatesForComponent(componentId) {
  return Object.values(TEMPLATES).filter((t) => t.component === componentId);
}

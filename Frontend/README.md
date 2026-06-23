# Divine Sky Work Order Studio

A manufacturing drawing generator frontend for altar production work orders.

## Setup

```bash
npm install
cp .env.example .env   # set VITE_API_BASE_URL to your backend
npm run dev
```

## Architecture

- **`src/data/templates.js`** — single source of truth. Each template declares
  `sharedFields`, `specificFields`, and `generatedDimensions`. Adding a new
  module (Pillars, Doors, Drawers, Crown, Base Box variants) means adding an
  entry here — no UI code changes.
- **`src/utils/mergeFields.js`** — the shared-field merge engine. Given the
  user's selected templates, it dedupes fields used by more than one template
  into a single "Common Dimensions" group, and groups the rest per-template.
- **`src/store/useWorkOrderStore.js`** — Zustand store (persisted to
  localStorage) holding selected components, selected templates per
  component, merged field values, and generation history.
- **`src/services/api.js`** — Axios client wrapping `GET /templates` and
  `POST /generate`. Base URL comes from `VITE_API_BASE_URL`.
- **`src/features/workspace/`** — the Engineering Workspace: `DimensionCard`
  (editable property-panel-style input, not a form field), `EngineeringPreview`
  (live SVG blueprint preview, client-side only, no backend calls), and
  `DimensionLegend` (collapsible abbreviation key).
- **`src/pages/`** — the five-step flow: Welcome → Build Altar → Choose
  Design → Workspace → Result.

## Flow

1. **Welcome** — hero + "Create New Work Order"
2. **Build Your Altar** — visual component picker (Ceiling, Base Box live;
   Pillars/Doors/Drawers/Crown marked "Coming Soon")
3. **Choose Design** — template cards per selected component (3 Dome /
   4 Dome Ceiling, Standard Base Box)
4. **Engineering Workspace** — dynamic dimension cards generated from
   metadata, with common fields merged, plus a live preview and Generate
   button
5. **Result** — generated drawing(s), dimension values, download actions

## Adding a new module

1. Add the component to `COMPONENTS` in `src/data/templates.js`.
2. Add one or more templates under `TEMPLATES`, referencing field keys from
   `FIELD_LIBRARY` (add new ones there if needed).
3. Add any new dimension abbreviations to `DIMENSION_LEGEND`.

Nothing else needs to change — the Build, Design, and Workspace pages all
render from this metadata.

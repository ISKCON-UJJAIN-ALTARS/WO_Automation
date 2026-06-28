# Divine Sky — Cutting Work Order Frontend

React + Vite frontend for the Divine Sky Cutting Work Order Generator backend.

Lets a designer pick a component type (Ceiling / Base Box), pick a variant
(3 Dome, 4 Dome, etc.), enter altar dimensions, and generate a finished
cutting-drawing PNG with all calculated values — without touching Excel by
hand.

## How it maps to the backend

This app is a pure client for the existing FastAPI backend
(`WO_Automation/backend`). It does not perform any calculations itself —
every number on the generated drawing comes from the backend's Excel
workbook, exactly as designed in that project.

| Frontend step                     | Backend touchpoint                                   |
| ---------------------------------- | ------------------------------------------------------ |
| Health check / API status dot      | `GET /templates`                                       |
| "Generate Drawing" button          | `POST /generate` with `{ template, inputs }`            |
| "Download PNG" button              | `GET /generate/download?filename=...`                   |
| Drawing preview `<img>`            | the static `image_path` returned by `/generate`         |

Template keys used in requests (`template` field) are exactly the keys in
the backend's `app/config/template_mappings.json`:

- `3dome_ceiling`
- `4dome_ceiling`

`basebox_standard` is included in the UI (with a visible "No config yet"
flag) because the backend already has a Pydantic schema for Base Box inputs,
but no `template_mappings.json` entry or Excel sheet yet. Submitting it will
get a 404 from `/generate` until that config is added on the backend — at
which point this UI works for it with no frontend changes.

## Project structure

```
src/
  api.js                  fetch wrappers for the three real endpoints
  templateConfig.js       category/variant/field data, mirrors backend config
  hooks/
    useApiHealth.js        tracks API base URL + live/dead status
  components/
    BlueprintIcon.jsx      mini line-drawing icons for cards
    SelectCard.jsx         category/variant selection card
    StepTrail.jsx          dimension-line styled step breadcrumb
    DimensionField.jsx     arrowed dimension-line input
    ResultView.jsx         generated image + calculated values table
  App.jsx                  3-step wizard: category -> variant -> dimensions
  index.css                design system (drafting-paper palette/type)
```

## Setup

Requires Node.js 18+.

```bash
npm install
cp .env.example .env   # adjust VITE_API_BASE if your backend isn't on localhost:8000
npm run dev
```

The dev server starts on `http://localhost:5173` by default. The API base
URL is also editable live in the running app's header, so you don't need to
restart the dev server to point at a different backend.

### Build for production

```bash
npm run build    # outputs to dist/
npm run preview  # serve the production build locally to sanity-check it
```

## Backend CORS requirement

The backend and frontend run on different origins during development
(`:8000` vs `:5173`), so the FastAPI backend needs CORS enabled or every
fetch call from this app will be blocked by the browser. Add this to
`backend/app/main.py`:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten this once you know where the frontend is hosted
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Known backend gaps this UI surfaces honestly rather than hiding

- **Base Box has no backend config yet** — the variant card shows a gray
  "No config yet" flag instead of pretending the flow works.
- **3-Dome drawing placeholders vs. config output keys mismatch** — the
  actual `{TAG}` placeholders burned into `templates/3dome_ceiling.png`
  (`TW, BW, UW, TH, LW, BH, VH, TL, VL, BL`) don't match the
  `output_mappings` keys in `template_mappings.json`
  (`TL, TSH, OW, INP, ...`). This frontend just renders whatever key/value
  pairs `/generate` returns, so it won't error — but the rendered drawing
  may not get every value placed where you'd expect until that mapping is
  reconciled on the backend.

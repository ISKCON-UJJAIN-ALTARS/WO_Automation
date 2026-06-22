# Divine Sky – Work Order Automation Backend

A FastAPI backend that accepts altar input dimensions, writes them into an Excel workbook,
reads back calculated outputs, detects `{PLACEHOLDER}` tags inside a template image via OCR,
replaces them with real values, and returns the path of the generated image.

---

## Quick Start

```bash
# 1. Install system dependencies (Ubuntu / Debian)
sudo apt-get install tesseract-ocr libgl1

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Run the server
cd backend
uvicorn app.main:app --reload
```

Swagger UI → http://127.0.0.1:8000/docs

---

## Example API Call

```bash
curl -X POST http://127.0.0.1:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "template": "4dome_ceiling",
    "inputs": {
      "altar_length": 42,
      "altar_depth": 22,
      "pillar_width": 3.5,
      "pillar_height": 25,
      "arch_ratio": 1.588
    }
  }'
```

**Response**

```json
{
  "success": true,
  "image_path": "/generated/4dome_ceiling_1718000000000.png",
  "values": {
    "TL": 8.75, "TSH": 3.5, "OW": 1.75, "INP": 17.5,
    "BSH": 3.5, "BSW": 3.5, "INW": 15.0, "INC": 1.75,
    "RBL": 0.875, "SL": 22.0, "LP": 22.0, "SW": 1.0,
    "SH": 5.5, "WP": 28.0, "PH": 28.5, "PL": 22.0
  }
}
```

The generated PNG is also served as a static file:

```
GET http://127.0.0.1:8000/generated/4dome_ceiling_1718000000000.png
```

---

## Folder Structure

```
backend/
├── app/
│   ├── main.py                      ← FastAPI app & startup
│   ├── routes/
│   │   └── templates.py             ← POST /generate endpoint
│   ├── services/
│   │   ├── excel_service.py         ← Write inputs / read outputs
│   │   ├── template_service.py      ← Replace placeholders in image
│   │   └── ocr_service.py           ← Detect {TAG} bounding boxes
│   ├── schemas/
│   │   └── request_models.py        ← Pydantic request/response models
│   └── config/
│       └── template_mappings.json   ← Cell & image path mappings
├── excel/
│   └── work_order.xlsx              ← Live calculation workbook
├── templates/
│   ├── 4dome_ceiling.png            ← Template image with {TAG} placeholders
│   └── 3dome_ceiling.png
├── generated/                       ← Output images land here (auto-created)
└── requirements.txt
```

---

## File Descriptions

### `app/main.py`
Creates the FastAPI application, configures structured logging to stdout,
mounts the `generated/` directory as a static file server (`/generated/*`),
and registers the route router. The `@app.on_event("startup")` hook logs a
startup confirmation.

### `app/routes/templates.py`
Contains three endpoints:
- **`POST /generate`** – Main workflow: validates the template key, delegates to
  `excel_service` and `template_service`, and returns a `GenerateResponse`.
- **`GET /generate/download?filename=…`** – Streams a previously generated PNG
  to the client as a file download.
- **`GET /templates`** – Lists all template keys registered in the config.

All business logic lives in the service layer; the route layer only marshals
requests/responses and translates service exceptions into HTTP errors.

### `app/services/excel_service.py`
Single public function: `write_inputs_and_read_outputs(inputs, input_mappings, output_mappings, sheet_name)`.
1. Opens `excel/work_order.xlsx` with `openpyxl` (formula mode).
2. Writes each input value to its configured cell address (`D1`, `D2`, …).
3. Saves the workbook.
4. Re-opens the same file with `data_only=True` to read back cached formula results.
5. Returns a dict of `{label: value}` pairs.

**Note:** Excel must have been opened and saved by a full spreadsheet engine (Excel,
LibreOffice) at least once for `data_only` to return real values. In production, add
a LibreOffice recalculation step (see the `xlsx` skill) or switch to `xlwings`.

### `app/services/ocr_service.py`
Uses `pytesseract` (with `--psm 11` sparse-text mode) to scan a BGR numpy array
for tokens matching `{UPPERCASE_KEY}`. Returns a list of `PlaceholderMatch` dataclasses,
each carrying the token string, the extracted key, and the pixel bounding box `(x, y, w, h)`.

### `app/services/template_service.py`
Public function: `render_template(template_path, values) -> Path`.
1. Loads the PNG with OpenCV.
2. Calls `ocr_service.detect_placeholders` to get all `{TAG}` bounding boxes.
3. For each found placeholder whose key exists in `values`:
   - Samples the median surrounding pixel colour to use as cover fill.
   - Draws a filled rectangle over the placeholder area.
   - Centres the numeric value string inside the same box using `cv2.putText`.
4. Writes the result to `generated/<stem>_<timestamp_ms>.png`.
5. Returns the absolute `Path` of the saved image.

### `app/schemas/request_models.py`
Pydantic v2 models:
- **`GenerateRequest`** – `template: str` + `inputs: Dict[str, float]`.
- **`GenerateResponse`** – `success: bool`, `image_path: str`, `values: Dict[str, Any]`.
Includes a schema example for Swagger UI documentation.

### `app/config/template_mappings.json`
Central configuration file. Each top-level key is a template identifier (e.g.
`"4dome_ceiling"`). Each entry specifies:
- `template_image` – relative path to the PNG inside the project root.
- `input_mappings` – maps field name → Excel cell (e.g. `"altar_length": "D1"`).
- `output_mappings` – maps output label → Excel cell (e.g. `"TL": "E1"`).
- `sheet_name` – the worksheet tab to target (e.g. `"4Dome"`).

**Adding a new template requires only:**
1. Place the PNG in `templates/`.
2. Add an entry here – no Python changes needed.

### `excel/work_order.xlsx`
The live Excel workbook. Contains two sheets (`4Dome`, `3Dome`).
- Column **D** (`D1`–`D6`): input cells written by `excel_service`.
- Column **E** (`E1`–`E16`): formula cells that compute the 16 output dimensions.
The formulas use standard altar geometry relationships (bay width, pillar ratios, etc.)
and should be replaced or extended with the real engineering formulas.

### `templates/4dome_ceiling.png` / `templates/3dome_ceiling.png`
Blueprint-style template images pre-printed with red-boxed `{TAG}` OCR placeholder
tokens at the correct dimensional annotation positions. Tesseract will detect these
tokens at runtime. Replace with actual production engineering drawings in the same
format (placeholder tokens rendered in a clean, high-contrast font).

### `generated/`
Output directory for rendered work-order images. Created automatically at startup.
Files are named `<template_key>_<unix_ms_timestamp>.png` and are immediately
accessible via the static file mount at `/generated/…`.

### `requirements.txt`
Python dependencies:
- `fastapi` + `uvicorn[standard]` – ASGI web framework
- `openpyxl` – Excel read/write without COM automation
- `Pillow` – Image creation for templates
- `opencv-python-headless` – Image manipulation and text rendering
- `pytesseract` – Python wrapper for Tesseract OCR engine
- `python-multipart` – Required by FastAPI for form-data support

---

## Adding a New Temple Type (Zero Code Changes)

1. Create your drawing with `{TAG}` tokens in it and save as `templates/my_new_altar.png`.
2. Add a new entry to `app/config/template_mappings.json`:

```json
"my_new_altar": {
  "template_image": "templates/my_new_altar.png",
  "input_mappings": {
    "altar_length": "D1",
    "altar_depth":  "D2"
  },
  "output_mappings": {
    "TL": "E1",
    "WP": "E2"
  },
  "sheet_name": "MyAltar"
}
```

3. Add the corresponding sheet to `excel/work_order.xlsx`.
4. Restart the server – the new template is immediately available.

---

## Production Notes

| Topic | Recommendation |
|---|---|
| Excel recalculation | Use LibreOffice headless (`python scripts/recalc.py`) or `xlwings` to force formula evaluation before reading `data_only` |
| OCR accuracy | Render placeholder tokens in a clean, large, high-contrast monospaced font; run Tesseract with `--psm 6` (uniform block) if tags are always aligned |
| Concurrency | The Excel workbook is written sequentially; add a file lock (`filelock`) for multi-worker deployments |
| Storage | Mount `generated/` to S3 or similar; add a cleanup job for old files |
| Auth | Add OAuth2 / API-key middleware in `app/main.py` before production use |

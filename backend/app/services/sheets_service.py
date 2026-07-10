import json
import logging
import os
import time
from typing import Dict, Any

import gspread
from google.auth.exceptions import GoogleAuthError
from gspread.exceptions import (
    SpreadsheetNotFound,
    WorksheetNotFound,
    APIError,
)

logger = logging.getLogger(__name__)

# ── Configuration (from environment) ───────────────────────────────────────────
_CREDENTIALS_JSON = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
_CREDENTIALS_PATH = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_PATH")
_SPREADSHEET_ID = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID")

_RECALC_SETTLE_SECONDS = float(os.environ.get("GOOGLE_SHEETS_RECALC_DELAY", "1.5"))

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client

    if _CREDENTIALS_JSON:
        try:
            info = json.loads(_CREDENTIALS_JSON)
        except json.JSONDecodeError as exc:
            raise FileNotFoundError(
                "GOOGLE_SHEETS_CREDENTIALS_JSON is set but is not valid JSON. "
                "Make sure you pasted the entire contents of the service-"
                f"account key file, with no extra quoting. Error: {exc}"
            )
        try:
            _client = gspread.service_account_from_dict(info)
        except GoogleAuthError:
            logger.exception("Failed to authenticate with Google Sheets (from JSON env var)")
            raise
        return _client

    if not _CREDENTIALS_PATH:
        raise FileNotFoundError(
            "Neither GOOGLE_SHEETS_CREDENTIALS_JSON nor "
            "GOOGLE_SHEETS_CREDENTIALS_PATH is set. Set one of them — the "
            "JSON env var for production (e.g. Render), or the file path "
            "for local development."
        )
    if not os.path.exists(_CREDENTIALS_PATH):
        raise FileNotFoundError(
            f"Google service-account credentials file not found at "
            f"'{_CREDENTIALS_PATH}'. Check GOOGLE_SHEETS_CREDENTIALS_PATH."
        )

    try:
        _client = gspread.service_account(filename=_CREDENTIALS_PATH)
    except GoogleAuthError:
        logger.exception("Failed to authenticate with Google Sheets")
        raise

    return _client


def _get_spreadsheet():
    if not _SPREADSHEET_ID:
        raise FileNotFoundError(
            "GOOGLE_SHEETS_SPREADSHEET_ID is not set. Add it to your .env "
            "file — it's the long ID in the sheet's URL between /d/ and /edit."
        )

    client = _get_client()
    try:
        return client.open_by_key(_SPREADSHEET_ID)
    except SpreadsheetNotFound:
        logger.error(
            "Spreadsheet with ID '%s' not found, or not shared with the "
            "service account. Open the sheet, click Share, and add the "
            "service account's client_email as an Editor.",
            _SPREADSHEET_ID,
        )
        raise


def write_inputs_and_read_outputs(
    inputs: Dict[str, float],
    input_mappings: Dict[str, str],
    output_mappings: Dict[str, str],
    input_sheet: str,
    output_sheet: str,
) -> Dict[str, Any]:
    """
    Write input values into the Google Sheet using the cell mappings, give
    Sheets a moment to recalculate formulas, then read back the calculated
    outputs.

    Output mappings with a blank/empty cell address (e.g. a template config
    entry like {"RBL": ""} for a value not yet wired up) are skipped rather
    than sent to the Sheets API — an empty range would otherwise cause
    batch_get() to fail for the ENTIRE template, not just that one field.
    Skipped labels are still included in the returned dict, with value None.
    """
    spreadsheet = _get_spreadsheet()

    # ── Write inputs ──────────────────────────────────────────────────────────
    logger.info("Opening worksheet for writing: '%s'", input_sheet)
    try:
        ws_input = spreadsheet.worksheet(input_sheet)
    except WorksheetNotFound:
        available = [ws.title for ws in spreadsheet.worksheets()]
        raise ValueError(
            f"Input sheet '{input_sheet}' not found. Available: {available}"
        )

    batch_data = []
    for field, cell_addr in input_mappings.items():
        value = inputs.get(field)
        if value is None:
            logger.warning("Input '%s' not provided; skipping %s", field, cell_addr)
            continue
        batch_data.append({"range": cell_addr, "values": [[value]]})
        logger.info("  Queued write %s -> %s = %s", field, cell_addr, value)

    if not batch_data:
        logger.warning("No inputs to write — all values were missing.")
    else:
        logger.info("Writing %d input(s) to '%s' ...", len(batch_data), input_sheet)
        try:
            ws_input.batch_update(batch_data, value_input_option="USER_ENTERED")
        except APIError:
            logger.exception("Google Sheets API error while writing inputs")
            raise
        logger.info("Inputs written successfully.")

    # ── Let formulas settle ────────────────────────────────────────────────────
    if _RECALC_SETTLE_SECONDS > 0:
        time.sleep(_RECALC_SETTLE_SECONDS)

    # ── Read outputs ────────────────────────────────────────────────────────────
    logger.info("Opening worksheet for reading: '%s'", output_sheet)
    try:
        ws_output = spreadsheet.worksheet(output_sheet)
    except WorksheetNotFound:
        available = [ws.title for ws in spreadsheet.worksheets()]
        raise ValueError(
            f"Output sheet '{output_sheet}' not found. Available: {available}"
        )

    # Filter out any mapping with no cell address before hitting the API —
    # a single blank range in the batch would otherwise fail the whole read.
    valid_output_mappings = {k: v for k, v in output_mappings.items() if v}
    skipped_labels = set(output_mappings) - set(valid_output_mappings)
    if skipped_labels:
        logger.warning(
            "Skipping output(s) with no cell mapping configured: %s",
            sorted(skipped_labels),
        )

    outputs: Dict[str, Any] = {label: None for label in skipped_labels}

    output_cells = list(valid_output_mappings.values())
    if output_cells:
        logger.info("Reading %d output cell(s) from '%s' ...", len(output_cells), output_sheet)
        try:
            # batch_get returns a list of value-ranges, one per requested range,
            # each itself a list-of-rows-of-cells (so [[value]] for a single cell).
            results = ws_output.batch_get(output_cells)
        except APIError:
            logger.exception("Google Sheets API error while reading outputs")
            raise

        for (label, cell_addr), result in zip(valid_output_mappings.items(), results):
            raw = result[0][0] if result and result[0] else None
            value = _coerce_numeric(raw)
            outputs[label] = value
            logger.debug("  Read %s <- %s = %s", label, cell_addr, value)
    else:
        logger.warning("No valid output cells to read — all mappings were blank.")

    logger.info("Outputs read: %s", outputs)
    return outputs


def _coerce_numeric(raw: Any) -> Any:
    """Convert a string cell value to int/float where possible, else pass through."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        return raw
    try:
        as_float = float(raw)
        return int(as_float) if as_float.is_integer() else as_float
    except (TypeError, ValueError):
        return raw
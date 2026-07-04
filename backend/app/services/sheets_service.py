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
# Two ways to supply credentials, checked in this order:
#
# 1. GOOGLE_SHEETS_CREDENTIALS_JSON — the *entire contents* of the
#    service-account JSON key file, pasted as a single environment variable
#    value. This is the one to use on Render (and any host where you can't
#    upload a file) since env vars are just strings.
#
# 2. GOOGLE_SHEETS_CREDENTIALS_PATH — a path to the JSON key file on disk.
#    This is the one to use for local development, where the file simply
#    lives in your project folder (and is git-ignored).
#
# GOOGLE_SHEETS_SPREADSHEET_ID: the spreadsheet ID from the sheet's URL
#                                (the segment between /d/ and /edit).
_CREDENTIALS_JSON = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
_CREDENTIALS_PATH = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_PATH")
_SPREADSHEET_ID = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID")

# Recalculation in Google Sheets happens server-side the instant a cell is
# written — there is no LibreOffice-style headless recalculation step here.
# We still pause briefly after writing inputs before reading outputs, purely
# to give Sheets' dependency graph a moment to settle for chained/volatile
# formulas, mirroring how the old code waited on a LibreOffice subprocess.
_RECALC_SETTLE_SECONDS = float(os.environ.get("GOOGLE_SHEETS_RECALC_DELAY", "1.5"))

_client = None


def _get_client():
    """
    Lazily create and cache the authenticated gspread client.

    Tries GOOGLE_SHEETS_CREDENTIALS_JSON first (raw JSON string — used on
    Render/production), then falls back to GOOGLE_SHEETS_CREDENTIALS_PATH
    (a file on disk — used for local development).

    Raises:
        FileNotFoundError: if neither credential source is configured, the
                            JSON string is malformed, or the file path does
                            not exist.
        GoogleAuthError:   if the credentials are invalid/unauthorized.
    """
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
    """
    Open the configured spreadsheet by ID.

    Raises:
        FileNotFoundError: if GOOGLE_SHEETS_SPREADSHEET_ID is unset.
        SpreadsheetNotFound: if the ID is wrong or the sheet isn't shared
                             with the service account's email.
    """
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

    This has the same signature and behaviour contract as the Excel-based
    write_inputs_and_read_outputs() it replaces, so callers (routes/templates.py)
    do not need to change.

    Args:
        inputs:          dict of field_name -> value supplied by the client
        input_mappings:  dict of field_name -> cell address (e.g. "D1")
        output_mappings: dict of label -> cell address (e.g. "TL" -> "E8")
        input_sheet:     name of the worksheet (tab) to write inputs into
        output_sheet:    name of the worksheet (tab) to read outputs from

    Returns:
        dict of label -> calculated value read from the sheet

    Raises:
        FileNotFoundError: missing credentials/spreadsheet configuration
        ValueError:        the named worksheet tab does not exist
        Exception:         any other Google API error (auth, quota, network)
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

    # Batch every input write into a single API call instead of one call per
    # cell. This is both faster and avoids Google Sheets API rate limits,
    # which is a real concern this design didn't have to worry about when
    # writes were just in-memory openpyxl cell assignments.
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
    # Google Sheets recalculates synchronously on write for most formulas, but
    # a short pause avoids reading stale values for chained/volatile formulas
    # immediately after a batch write.
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

    output_cells = list(output_mappings.values())
    logger.info("Reading %d output cell(s) from '%s' ...", len(output_cells), output_sheet)
    try:
        # batch_get returns a list of value-ranges, one per requested range,
        # each itself a list-of-rows-of-cells (so [[value]] for a single cell).
        results = ws_output.batch_get(output_cells)
    except APIError:
        logger.exception("Google Sheets API error while reading outputs")
        raise

    outputs: Dict[str, Any] = {}
    for (label, cell_addr), result in zip(output_mappings.items(), results):
        raw = result[0][0] if result and result[0] else None
        # Sheets API returns everything as strings; coerce to a number when
        # possible so downstream rendering (e.g. float formatting) still works
        # the same way it did when openpyxl handed back native numeric types.
        value = _coerce_numeric(raw)
        outputs[label] = value
        logger.debug("  Read %s <- %s = %s", label, cell_addr, value)

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
        # Preserve whole numbers as ints for cleaner display, matching the
        # kind of values openpyxl would have returned for integer cells.
        return int(as_float) if as_float.is_integer() else as_float
    except (TypeError, ValueError):
        return raw

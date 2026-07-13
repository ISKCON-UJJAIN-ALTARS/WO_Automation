import json
from pathlib import Path

_CONFIG_DIR = Path(__file__).resolve().parent

with (_CONFIG_DIR / "cell_groups.json").open() as fh:
    _CELL_GROUPS: dict = json.load(fh)

with (_CONFIG_DIR / "field_catalog.json").open() as fh:
    _FIELD_CATALOG: dict = json.load(fh)

with (_CONFIG_DIR / "templates.json").open() as fh:
    _TEMPLATES_RAW: dict = json.load(fh)


def _resolve_template(name: str, raw: dict) -> dict:
    group = _CELL_GROUPS[raw["input_group"]]
    keys = raw.get("input_fields") or list(group["cells"].keys())

    input_mappings = {k: group["cells"][k] for k in keys}

    input_fields = [
        {
            "key": k,
            "cell": group["cells"][k],
            **_FIELD_CATALOG.get(k, {}),
        }
        for k in keys
    ]

    return {
        "template_image": raw["template_image"],
        "input_sheet": raw.get("input_sheet") or group["sheet"],
        "output_sheet": raw["output_sheet"],
        "input_mappings": input_mappings,      # same shape as before — sheets_service needs no changes
        "output_mappings": raw["output_mappings"],
        "input_fields": input_fields,          # new — for frontend form rendering
    }


def load_template_config() -> dict:
    """Returns the fully resolved template config, same flat shape the router already expects,
    plus an extra 'input_fields' key per template for building dropdowns/labels in the UI."""
    return {name: _resolve_template(name, raw) for name, raw in _TEMPLATES_RAW.items()}
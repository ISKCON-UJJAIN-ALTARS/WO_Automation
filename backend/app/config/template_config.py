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
    # image_fields: fields that only drive which shape variant image gets
    # picked (e.g. pillar_config, component_box). They still show up on the
    # form and are still required, but they don't correspond to an Excel
    # cell yet, so they're kept out of input_mappings entirely.
    image_keys = raw.get("image_fields") or []

    input_mappings = {k: group["cells"][k] for k in keys}

    input_fields = [
        {
            "key": k,
            "cell": group["cells"][k],
            **_FIELD_CATALOG.get(k, {}),
        }
        for k in keys
    ] + [
        {
            "key": k,
            "cell": None,
            "for_image_only": True,
            **_FIELD_CATALOG.get(k, {}),
        }
        for k in image_keys
    ]

    return {
        "template_image": raw["template_image"],
        "image_rule": raw.get("image_rule"),   # new — drives auto image selection
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
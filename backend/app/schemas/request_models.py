from pydantic import BaseModel, Field, model_validator
from typing import Dict, Any, Literal, Union, Annotated


# ── Loose input container — real validation happens against the resolved config ──

class TemplateInputs(BaseModel):
    """Accepts any float/int/str fields; router validates required keys against
    the resolved template config (input_fields) before writing to Excel."""
    model_config = {"extra": "allow"}

    def as_dict(self) -> Dict[str, Any]:
        return self.model_dump()


# ── Single request model — template drives which fields are required ─────────

ALL_TEMPLATE_KEYS = Literal[
    "3dome_ceiling",
    "4dome_ceiling",
    "top",
    "side_cutting",
    "bottom",
    "middle_cutting",
]


class GenerateRequest(BaseModel):
    template: ALL_TEMPLATE_KEYS
    inputs: TemplateInputs

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "template": "4dome_ceiling",
                    "inputs": {
                        "altar_length": 42,
                        "altar_depth": 22,
                        "pillar_width": 3.5,
                        "pillar_height": 25,
                        "arch_ratio": 1.588,
                    },
                },
                {
                    "template": "bottom",
                    "inputs": {
                        "box_length": 42,
                        "box_height": 18,
                        "level_count": 3,
                        "box_design": "standard",
                        "level_1D": 12,
                        "level_2D": 10,
                        "level_3D": 8,
                    },
                },
            ]
        }
    }


# ── Response (unchanged) ──────────────────────────────────────────────────────

class GenerateResponse(BaseModel):
    success: bool
    image_path: str
    values: Dict[str, Any]
from pydantic import BaseModel, Field
from typing import Dict, Any, Literal, Union, Annotated


# ── Input schemas per altar type ──────────────────────────────────────────────

class CeilingInputs(BaseModel):
    altar_length: float
    altar_depth:  float
    pillar_width: float
    pillar_height: float
    arch_ratio:   float


class BaseBoxInputs(BaseModel):
    altar_length: float
    altar_depth:  float
    altar_height: float
    shelf_count:  int
    door_width:   float
    # add whatever fields basebox actually needs


# ── Discriminated request models ──────────────────────────────────────────────

class CeilingRequest(BaseModel):
    template: Literal["3dome_ceiling", "4dome_ceiling"]
    inputs:   CeilingInputs

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
                        "arch_ratio": 1.588
                    }
                }
            ]
        }
    }


class BaseBoxRequest(BaseModel):
    template: Literal[
        "top",
        "back",
        "bottom",
        "step_0",
        "step_1",
        "step_2",
        "step_3",
    ]
    inputs:   BaseBoxInputs

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "template": "basebox_standard",
                    "inputs": {
                        "altar_length": 42,
                        "altar_depth": 22,
                        "altar_height": 18,
                        "shelf_count": 2,
                        "door_width": 12.5
                    }
                }
            ]
        }
    }


# ── Union type used in the router ─────────────────────────────────────────────

GenerateRequest = Annotated[
    Union[CeilingRequest, BaseBoxRequest],
    Field(discriminator="template")
]


# ── Response (shared) ─────────────────────────────────────────────────────────

class GenerateResponse(BaseModel):
    success:    bool
    image_path: str
    values:     Dict[str, Any]
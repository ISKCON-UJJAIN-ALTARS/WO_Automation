from pydantic import BaseModel, Field
from typing import Dict, Any


class GenerateRequest(BaseModel):
    template: str = Field(..., description="Template key, e.g. '4dome_ceiling'")
    inputs: Dict[str, float] = Field(..., description="Input dimension values keyed by field name")

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


class GenerateResponse(BaseModel):
    success: bool
    image_path: str
    values: Dict[str, Any]

from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


class PestRead(BaseModel):
    id: int
    name_ko: str
    name_en: str
    name_scientific: Optional[str]
    body_size_mm_min: Optional[float]
    body_size_mm_max: Optional[float]
    color_pattern: Optional[str]
    wing_pattern: Optional[str]
    visual_features: Optional[List[str]]
    active_season: Optional[str]
    preferred_temperature: Optional[str]
    lifecycle_days: Optional[int]
    basic_control_methods: Optional[List[str]]
    priority_weight: float

    class Config:
        from_attributes = True


class PestList(BaseModel):
    total: int
    items: List[PestRead]

from pydantic import BaseModel
from typing import Optional, List, Dict


class HabitatRead(BaseModel):
    id: int
    name_ko: str
    name_en: str
    category: str
    description: Optional[str]
    risk_level: int
    visual_keywords: Optional[List[str]]
    seasonal_risk: Optional[Dict[str, int]]
    removal_tips: Optional[List[str]]

    class Config:
        from_attributes = True

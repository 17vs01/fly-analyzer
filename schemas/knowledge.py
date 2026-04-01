from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class KnowledgeCreate(BaseModel):
    pest_id: Optional[int] = None
    pest_name_raw: Optional[str] = None
    knowledge_type: str = Field(..., pattern="^(habitat|control|behavior|other)$")
    title: str = Field(..., min_length=2, max_length=200)
    content: str = Field(..., min_length=10)
    location_type: Optional[str] = None
    season_observed: Optional[str] = None
    tags: Optional[List[str]] = []
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)


class KnowledgeRead(KnowledgeCreate):
    id: int
    chroma_doc_id: Optional[str]
    use_count: int
    is_verified: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class ReportCreate(BaseModel):
    """이미지 분석 요청 시 사용 (내부용, 파일 업로드는 Form으로 처리)"""
    pass


class ReportRead(BaseModel):
    id: int
    image_path: str
    pest_id: Optional[int]
    pest_confidence: Optional[float]
    pest_candidates: Optional[List[Dict[str, Any]]]
    detected_habitats: Optional[List[Dict[str, Any]]]
    applied_knowledge: Optional[List[Dict[str, Any]]]
    immediate_actions: Optional[List[str]]
    short_term_actions: Optional[List[str]]
    long_term_actions: Optional[List[str]]
    summary_text: Optional[str]
    status: str
    is_low_confidence: bool
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True

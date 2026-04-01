"""
models/habitat.py - 서식지 및 오염원 정보
AI가 사진 배경에서 감지할 수 있는 오염원 목록
"""
from sqlalchemy import Column, Integer, String, Text, JSON, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from database import Base


class Habitat(Base):
    """서식지/오염원 테이블"""
    __tablename__ = "habitats"

    id = Column(Integer, primary_key=True, index=True)

    # ── 기본 정보 ──────────────────────────────────────────
    name_ko = Column(String(100), nullable=False, comment="한국어 이름 (예: 배수구)")
    name_en = Column(String(100), nullable=False, comment="영어 이름")
    category = Column(String(50), nullable=False,
                      comment="카테고리: drain(배수구)/plant(식물)/food(음식)/waste(쓰레기)/other")

    # ── 설명 ──────────────────────────────────────────────
    description = Column(Text, comment="서식지 설명")
    risk_level = Column(Integer, default=1, comment="위험도 1~5 (5가 가장 위험)")

    # ── AI 이미지 인식용 특징 ───────────────────────────────
    visual_keywords = Column(JSON, comment="이미지에서 감지할 키워드 목록")

    # ── 계절별 위험도 ──────────────────────────────────────
    # {"spring": 2, "summer": 5, "fall": 3, "winter": 1}
    seasonal_risk = Column(JSON, comment="계절별 위험도 점수")

    # ── 제거 방법 ──────────────────────────────────────────
    removal_tips = Column(JSON, comment="이 서식지 제거 팁 목록")

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # ── 관계 ──────────────────────────────────────────────
    pest_links = relationship("PestHabitatLink", back_populates="habitat",
                              cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Habitat id={self.id} name={self.name_ko} category={self.category}>"

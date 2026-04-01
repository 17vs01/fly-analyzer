"""
models/pest.py - 해충 종 정보
새로운 해충 종을 추가하려면 seed_data.py에 데이터만 추가하면 됨
"""
from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from database import Base


class Pest(Base):
    """초파리 종 정보 테이블"""
    __tablename__ = "pests"

    id = Column(Integer, primary_key=True, index=True)

    # ── 기본 분류 정보 ─────────────────────────────────────
    name_ko = Column(String(100), nullable=False, comment="한국어 이름 (예: 얼룩점초파리)")
    name_en = Column(String(100), nullable=False, comment="영어 이름")
    name_scientific = Column(String(150), comment="학명")

    # ── 외형 특징 (AI 분류에 사용) ─────────────────────────
    body_size_mm_min = Column(Float, comment="몸 크기 최솟값 (mm)")
    body_size_mm_max = Column(Float, comment="몸 크기 최댓값 (mm)")
    color_pattern = Column(String(200), comment="색깔/무늬 설명")
    wing_pattern = Column(String(200), comment="날개 무늬")
    visual_features = Column(JSON, comment="AI 분류용 시각 특징 목록")

    # ── 생태 정보 ──────────────────────────────────────────
    active_season = Column(String(100), comment="주요 활동 계절")
    preferred_temperature = Column(String(50), comment="선호 온도 범위")
    lifecycle_days = Column(Integer, comment="알→성충 일수")

    # ── 방역 기본 지침 (문헌 기반, 낮은 우선순위) ─────────────
    basic_control_methods = Column(JSON, comment="기본 방역 방법 목록")

    # ── 메타데이터 ─────────────────────────────────────────
    priority_weight = Column(Float, default=1.0, comment="AI 가중치 (사용자 데이터로 조정)")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # ── 관계 ──────────────────────────────────────────────
    habitats = relationship("PestHabitatLink", back_populates="pest", cascade="all, delete-orphan")
    reports = relationship("AnalysisReport", back_populates="pest")
    knowledge_entries = relationship("UserKnowledge", back_populates="pest")

    def __repr__(self):
        return f"<Pest id={self.id} name={self.name_ko}>"


class PestHabitatLink(Base):
    """해충-서식지 연결 테이블 (다대다 관계)"""
    __tablename__ = "pest_habitat_links"

    id = Column(Integer, primary_key=True, index=True)
    pest_id = Column(Integer, ForeignKey("pests.id", ondelete="CASCADE"), nullable=False)
    habitat_id = Column(Integer, ForeignKey("habitats.id", ondelete="CASCADE"), nullable=False)

    # 이 해충이 이 서식지에서 얼마나 자주 발견되는지 (0.0 ~ 1.0)
    frequency_score = Column(Float, default=0.5, comment="발견 빈도 점수")

    # 데이터 출처 (문헌 vs 사용자 직접 입력)
    source = Column(String(20), default="literature", comment="literature | user_input")
    note = Column(Text, comment="추가 메모")

    # 관계
    pest = relationship("Pest", back_populates="habitats")
    habitat = relationship("Habitat", back_populates="pest_links")

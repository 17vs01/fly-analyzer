"""
models/knowledge.py - 사용자가 직접 입력한 현장 지식
★ 이 데이터는 문헌 정보보다 높은 우선순위(High Priority)로 처리됨
"""
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from database import Base


class UserKnowledge(Base):
    """사용자 커스텀 지식 테이블"""
    __tablename__ = "user_knowledge"

    id = Column(Integer, primary_key=True, index=True)

    # ── 어떤 해충에 대한 지식인지 ─────────────────────────────
    pest_id = Column(Integer, ForeignKey("pests.id", ondelete="SET NULL"), nullable=True,
                     comment="특정 해충과 연결 (없으면 일반 지식)")
    pest_name_raw = Column(String(100), comment="해충 이름 (pest_id 없을 때 직접 입력)")

    # ── 지식 내용 ─────────────────────────────────────────
    knowledge_type = Column(String(30), nullable=False,
                            comment="타입: habitat(서식지)/control(방역법)/behavior(행동)/other")
    title = Column(String(200), nullable=False, comment="지식 제목")
    content = Column(Text, nullable=False, comment="상세 내용 (벡터화되어 ChromaDB에도 저장)")

    # ── 현장 메타데이터 ────────────────────────────────────
    location_type = Column(String(100), comment="발견 장소 유형 (예: 음식점 주방)")
    season_observed = Column(String(20), comment="관찰 계절")
    tags = Column(JSON, comment="검색용 태그 목록")

    # ── 신뢰도 관리 ───────────────────────────────────────
    # 사용자 입력 기본값: 1.0 (문헌 데이터는 0.5로 설정하여 사용자 데이터 우선)
    confidence_score = Column(Float, default=1.0, comment="신뢰도 점수 (0.0~1.0)")
    is_verified = Column(Boolean, default=False, comment="전문가 검증 여부")

    # ── ChromaDB 연동 ──────────────────────────────────────
    chroma_doc_id = Column(String(200), comment="ChromaDB 문서 ID (삭제/업데이트용)")

    # ── 통계 ──────────────────────────────────────────────
    use_count = Column(Integer, default=0, comment="분석에 활용된 횟수")

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # ── 관계 ──────────────────────────────────────────────
    pest = relationship("Pest", back_populates="knowledge_entries")

    def __repr__(self):
        return f"<UserKnowledge id={self.id} type={self.knowledge_type} title={self.title[:30]}>"

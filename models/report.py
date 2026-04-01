"""
models/report.py - 방역 분석 보고서
사진 1장 분석 → 보고서 1건 생성
"""
from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, DateTime, JSON, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from database import Base


class AnalysisReport(Base):
    """방역 분석 보고서 테이블"""
    __tablename__ = "analysis_reports"

    id = Column(Integer, primary_key=True, index=True)

    # ── 입력 이미지 정보 ───────────────────────────────────
    image_path = Column(String(500), nullable=False, comment="업로드된 이미지 파일 경로")
    image_hash = Column(String(64), comment="중복 분석 방지용 이미지 해시")

    # ── 분석 결과: 해충 ────────────────────────────────────
    pest_id = Column(Integer, ForeignKey("pests.id", ondelete="SET NULL"), nullable=True)
    pest_confidence = Column(Float, comment="해충 분류 신뢰도 (0.0~1.0)")

    # 신뢰도가 낮을 때 후보 목록
    # [{"pest_id": 1, "name": "얼룩점초파리", "confidence": 0.8}, ...]
    pest_candidates = Column(JSON, comment="해충 후보 목록 (신뢰도 순)")

    # ── 분석 결과: 오염원/서식지 ───────────────────────────
    # [{"habitat_id": 2, "name": "배수구", "confidence": 0.9, "bbox": [x,y,w,h]}, ...]
    detected_habitats = Column(JSON, comment="감지된 오염원 목록")

    # ── 사용된 사용자 지식 목록 ────────────────────────────
    # [{"knowledge_id": 5, "title": "...", "relevance": 0.95}, ...]
    applied_knowledge = Column(JSON, comment="보고서 생성에 활용된 사용자 지식")

    # ── 최종 방역 지침 (보고서 본문) ─────────────────────────
    immediate_actions = Column(JSON, comment="즉시 실행 조치 목록")
    short_term_actions = Column(JSON, comment="단기 조치 (1주일 이내)")
    long_term_actions = Column(JSON, comment="장기 조치 (1개월 이내)")
    summary_text = Column(Text, comment="보고서 요약 텍스트")

    # ── 상태 ──────────────────────────────────────────────
    status = Column(String(20), default="pending",
                    comment="상태: pending/analyzing/completed/failed")
    is_low_confidence = Column(Boolean, default=False, comment="신뢰도 낮음 플래그")
    error_message = Column(Text, comment="오류 발생 시 메시지")

    # ── 사용자 피드백 ──────────────────────────────────────
    user_feedback_correct = Column(Boolean, nullable=True, comment="분석 결과가 맞는지 사용자 확인")
    user_feedback_note = Column(Text, comment="사용자 피드백 메모")

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    # ── 관계 ──────────────────────────────────────────────
    pest = relationship("Pest", back_populates="reports")

    def __repr__(self):
        return f"<AnalysisReport id={self.id} status={self.status}>"

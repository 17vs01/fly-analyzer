"""
services/image_analyzer.py - 분석 오케스트라 (지휘자)

전체 분석 흐름:
  [이미지 수신]
      ↓
  [품질 검사] → 흐림/어둠 → ❌ 재촬영 요청 메시지
      ↓ OK
  [DB 해충 정보 로드]
      ↓
  [3개 AI 동시 분석] Claude + OpenAI + YOLO
      ↓
  [앙상블 합산] 가중 투표
      ↓
  ★ [RAG 검색] 앙상블 결과로 사용자 지식 검색 → AI 보정 프롬프트 생성
      ↓
  [최종 결과 DB 저장]
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import AsyncSessionLocal
from models.pest import Pest
from models.report import AnalysisReport
from services.ai_providers.claude_analyzer import ClaudeAnalyzer
from services.ai_providers.openai_analyzer import OpenAIAnalyzer
from services.ai_providers.yolo_analyzer import YoloAnalyzer
from services.ensemble import EnsembleResult, EnsembleService
from services.image_quality import ImageQualityChecker
from services.rag_service import RetrievedKnowledge, rag_service

logger = logging.getLogger(__name__)

# ── 싱글톤 인스턴스 ──────────────────────────────────────────────────────────
_quality_checker = ImageQualityChecker()
_claude = ClaudeAnalyzer()
_openai = OpenAIAnalyzer()
_yolo = YoloAnalyzer()
_ensemble = EnsembleService()


async def analyze_image_task(report_id: int) -> None:
    """백그라운드 메인 분석 함수"""
    logger.info(f"🔍 분석 시작 | report_id={report_id}")

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AnalysisReport).where(AnalysisReport.id == report_id)
        )
        report = result.scalar_one_or_none()
        if not report:
            logger.error(f"report_id={report_id} 를 찾을 수 없습니다.")
            return

        try:
            report.status = "analyzing"
            await db.commit()

            # ── STEP 1: 이미지 품질 검사 ─────────────────────
            quality = _quality_checker.check(report.image_path)
            if not quality.is_ok:
                report.status = "needs_recapture"
                report.is_low_confidence = True
                report.summary_text = quality.message
                report.completed_at = datetime.now(timezone.utc)
                await db.commit()
                logger.info(f"📸 재촬영 요청 | 이유: {quality.issue}")
                return

            # ── STEP 2: DB 해충 정보 로드 ────────────────────
            pest_context = await _load_pest_context(db)

            # ── STEP 3: 3개 AI 동시 분석 ─────────────────────
            logger.info("🤖 AI 3개 병렬 분석 시작...")
            claude_result, openai_result, yolo_result = await asyncio.gather(
                _claude.analyze(report.image_path, pest_context),
                _openai.analyze(report.image_path, pest_context),
                _yolo.analyze(report.image_path, pest_context),
            )

            # ── STEP 4: 앙상블 합산 ───────────────────────────
            ensemble = _ensemble.combine([claude_result, openai_result, yolo_result])

            # ── STEP 5: ★ RAG - 사용자 지식 검색 ───────────────
            user_knowledge = _search_user_knowledge(ensemble)

            if user_knowledge:
                logger.info(f"📚 사용자 지식 {len(user_knowledge)}건 발견 → 보고서에 반영")
                # 앙상블 신뢰도가 낮았어도 사용자 지식이 있으면 재촬영 취소
                if ensemble.needs_recapture and ensemble.pest_name_ko:
                    ensemble.needs_recapture = False
                    ensemble.recapture_reason = ""

            # ── STEP 6: DB 해충 ID 조회 ──────────────────────
            pest_id = await _find_pest_id(db, ensemble.pest_name_ko)

            # ── STEP 7: 결과 저장 ─────────────────────────────
            await _save_result(db, report, ensemble, pest_id, user_knowledge)
            logger.info(f"✅ 분석 완료 | report_id={report_id} | 결과={ensemble.pest_name_ko}")

        except Exception as e:
            logger.error(f"분석 오류 | report_id={report_id} | {e}", exc_info=True)
            report.status = "failed"
            report.error_message = str(e)
            report.completed_at = datetime.now(timezone.utc)
            await db.commit()


def _search_user_knowledge(ensemble: EnsembleResult) -> list[RetrievedKnowledge]:
    """앙상블 결과를 바탕으로 관련 사용자 지식 검색"""
    # 검색 쿼리 구성: 해충명 + 감지된 서식지 이름
    habitat_names = " ".join(h["name_ko"] for h in ensemble.detected_habitats)
    query = f"{ensemble.pest_name_ko} {habitat_names} 방역 서식지".strip()

    return rag_service.search(
        query=query,
        pest_name=ensemble.pest_name_ko,
        top_k=5,
        min_relevance=0.3,
    )


async def _load_pest_context(db: AsyncSession) -> dict:
    result = await db.execute(select(Pest))
    pests = result.scalars().all()
    return {
        "pests": [
            {
                "name_ko": p.name_ko,
                "name_scientific": p.name_scientific,
                "visual_features": p.visual_features or [],
                "color_pattern": p.color_pattern,
                "wing_pattern": p.wing_pattern,
            }
            for p in pests
        ]
    }


async def _find_pest_id(db: AsyncSession, pest_name_ko: str) -> int | None:
    if not pest_name_ko:
        return None
    result = await db.execute(
        select(Pest.id).where(Pest.name_ko == pest_name_ko)
    )
    return result.scalar_one_or_none()


async def _save_result(
    db: AsyncSession,
    report: AnalysisReport,
    ensemble: EnsembleResult,
    pest_id: int | None,
    user_knowledge: list[RetrievedKnowledge],
) -> None:
    report.pest_id = pest_id
    report.pest_confidence = ensemble.pest_confidence
    report.pest_candidates = ensemble.pest_candidates
    report.detected_habitats = [
        {"name_ko": h["name_ko"], "confidence": h["confidence"]}
        for h in ensemble.detected_habitats
    ]
    report.is_low_confidence = ensemble.needs_recapture

    # ★ 사용된 사용자 지식 목록 기록
    report.applied_knowledge = [
        {
            "knowledge_id": k.knowledge_id,
            "title": k.title,
            "knowledge_type": k.knowledge_type,
            "relevance": k.relevance_score,
            "confidence": k.confidence_score,
        }
        for k in user_knowledge
    ]

    # ── 조치 목록 생성 ────────────────────────────────────
    report.immediate_actions = _build_immediate_actions(ensemble, user_knowledge)
    report.short_term_actions = _build_short_term_actions(ensemble)
    report.long_term_actions = _build_long_term_actions(ensemble)

    if ensemble.needs_recapture:
        report.status = "needs_recapture"
        report.summary_text = ensemble.recapture_reason
    else:
        report.status = "completed"
        knowledge_note = (
            f" (현장 전문가 지식 {len(user_knowledge)}건 반영)"
            if user_knowledge else ""
        )
        report.summary_text = (
            f"[{ensemble.pest_name_ko}] 분석 완료 "
            f"(신뢰도: {ensemble.pest_confidence:.0%}){knowledge_note}\n"
            f"감지된 오염원: {', '.join(h['name_ko'] for h in ensemble.detected_habitats)}"
        )

    report.completed_at = datetime.now(timezone.utc)
    await db.commit()


def _build_immediate_actions(
    ensemble: EnsembleResult,
    user_knowledge: list[RetrievedKnowledge],
) -> list[str]:
    """즉시 조치 목록 - 사용자 지식이 있으면 우선 반영"""
    actions: list[str] = []

    # ★ 사용자 지식 기반 조치 (최우선)
    for k in user_knowledge:
        if k.knowledge_type == "control":
            actions.append(f"[현장 검증됨] {k.title}")

    # 감지된 서식지 기반 기본 조치
    for h in ensemble.detected_habitats:
        if h["confidence"] >= 0.6:
            actions.append(f"⚠️ '{h['name_ko']}' 즉시 청소 및 제거")

    return actions


def _build_short_term_actions(ensemble: EnsembleResult) -> list[str]:
    """단기 조치 (1주일 이내) - 4단계에서 고도화"""
    return [
        f"트랩 설치 및 {ensemble.pest_name_ko or '해충'} 발생 모니터링",
        "서식 가능한 모든 유기물 제거",
        "환기 및 습도 관리",
    ]


def _build_long_term_actions(ensemble: EnsembleResult) -> list[str]:
    """장기 조치 (1개월 이내) - 4단계에서 고도화"""
    return [
        "방충망 점검 및 보수",
        "정기 방역 일정 수립 (월 1회 이상)",
        "오염원 구조적 차단 (배수구 커버 등)",
    ]

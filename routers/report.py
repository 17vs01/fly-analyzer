"""
routers/report.py - 보고서 출력 API

GET /reports/          → 보고서 목록 (★ pest_name_ko 실제 조회)
GET /reports/{id}      → JSON 보고서 전문
GET /reports/{id}/pdf  → PDF 다운로드
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from database import get_db
from models.report import AnalysisReport
from models.pest import Pest
from services.report_generator import report_generator

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/", summary="보고서 목록")
async def list_reports(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """최신 순으로 보고서 목록 반환. pest_name_ko 포함."""
    result = await db.execute(
        select(AnalysisReport)
        .order_by(desc(AnalysisReport.created_at))
        .limit(limit)
        .offset(offset)
    )
    reports = result.scalars().all()

    # ★ pest_id 목록 수집 후 한 번에 조회 (N+1 방지)
    pest_ids = {r.pest_id for r in reports if r.pest_id is not None}
    pest_name_map: dict[int, str] = {}
    if pest_ids:
        pest_result = await db.execute(
            select(Pest.id, Pest.name_ko).where(Pest.id.in_(pest_ids))
        )
        pest_name_map = {row.id: row.name_ko for row in pest_result}

    return {
        "total": len(reports),
        "items": [
            {
                "id": r.id,
                "status": r.status,
                "pest_name_ko": pest_name_map.get(r.pest_id) if r.pest_id else None,
                "pest_confidence": r.pest_confidence,
                "is_low_confidence": r.is_low_confidence,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reports
        ],
    }


@router.get("/{report_id}", summary="JSON 보고서 전문")
async def get_report_json(report_id: int, db: AsyncSession = Depends(get_db)):
    """모바일 앱 결과 화면용 전체 보고서 JSON."""
    report, pest = await _load_report_and_pest(report_id, db)
    full = report_generator.build(report)

    if pest:
        full.pest_name_ko = pest.name_ko

    return report_generator.to_dict(full)


@router.get("/{report_id}/pdf", summary="PDF 보고서 다운로드")
async def get_report_pdf(report_id: int, db: AsyncSession = Depends(get_db)):
    """PDF 파일 반환. Content-Type: application/pdf"""
    report, pest = await _load_report_and_pest(report_id, db)
    full = report_generator.build(report)

    if pest:
        full.pest_name_ko = pest.name_ko

    pdf_bytes = report_generator.to_pdf(full, pest_obj=pest)
    filename = f"pest_report_{report_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

async def _load_report_and_pest(report_id: int, db: AsyncSession):
    """보고서 + 해충 로드. 없거나 미완료면 예외 발생."""
    result = await db.execute(
        select(AnalysisReport).where(AnalysisReport.id == report_id)
    )
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다.")

    if report.status not in ("completed", "needs_recapture"):
        raise HTTPException(
            status_code=202,
            detail=f"분석 진행 중입니다. 현재 상태: {report.status}",
        )

    pest = None
    if report.pest_id:
        pest_result = await db.execute(
            select(Pest).where(Pest.id == report.pest_id)
        )
        pest = pest_result.scalar_one_or_none()

    return report, pest

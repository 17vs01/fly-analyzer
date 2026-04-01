"""
routers/report.py - Report output API

GET /reports/{id}          -> JSON report
GET /reports/{id}/pdf      -> PDF download
GET /reports/              -> Report list
"""
from __future__ import annotations

import io
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from database import get_db
from models.report import AnalysisReport
from models.pest import Pest
from services.report_generator import report_generator

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/", summary="Report list")
async def list_reports(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Returns the most recent reports (newest first)."""
    result = await db.execute(
        select(AnalysisReport)
        .order_by(desc(AnalysisReport.created_at))
        .limit(limit)
        .offset(offset)
    )
    reports = result.scalars().all()

    return {
        "total": len(reports),
        "items": [
            {
                "id": r.id,
                "status": r.status,
                "pest_name_ko": None,   # resolved below via pest_id
                "pest_confidence": r.pest_confidence,
                "is_low_confidence": r.is_low_confidence,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reports
        ],
    }


@router.get("/{report_id}", summary="Full JSON report")
async def get_report_json(report_id: int, db: AsyncSession = Depends(get_db)):
    """
    Returns the full structured report as JSON.
    Mobile app uses this to render the results screen.
    """
    report, pest = await _load_report_and_pest(report_id, db)
    full = report_generator.build(report)

    # Override pest_name_ko from joined pest object
    if pest:
        full.pest_name_ko = pest.name_ko

    return report_generator.to_dict(full)


@router.get("/{report_id}/pdf", summary="Download PDF report")
async def get_report_pdf(report_id: int, db: AsyncSession = Depends(get_db)):
    """
    Returns a PDF file for download.
    Content-Type: application/pdf
    """
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


# ── Internal helper ───────────────────────────────────────────────────────────

async def _load_report_and_pest(report_id: int, db: AsyncSession):
    """Load report + joined pest. Raises 404 if not found or not completed."""
    result = await db.execute(
        select(AnalysisReport).where(AnalysisReport.id == report_id)
    )
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")

    if report.status not in ("completed", "needs_recapture"):
        raise HTTPException(
            status_code=202,
            detail=f"Analysis in progress. Current status: {report.status}",
        )

    # Load pest details if available
    pest = None
    if report.pest_id:
        pest_result = await db.execute(
            select(Pest).where(Pest.id == report.pest_id)
        )
        pest = pest_result.scalar_one_or_none()

    return report, pest

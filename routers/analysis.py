"""
routers/analysis.py - 이미지 분석 API
POST /analysis/upload   → 이미지 업로드 + 분석 시작 (백그라운드)
GET  /analysis/{id}     → 분석 결과 조회
GET  /analysis/{id}/recapture → 재촬영 요청 메시지 조회
"""
import os
import hashlib
from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models.report import AnalysisReport
from schemas.report import ReportRead
from config import settings
from services.image_analyzer import analyze_image_task

router = APIRouter(prefix="/analysis", tags=["이미지 분석"])

Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)


@router.post("/upload", response_model=ReportRead, status_code=202, summary="이미지 업로드 & 분석 시작")
async def upload_and_analyze(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="초파리 사진 (jpg/png/webp)"),
    db: AsyncSession = Depends(get_db),
):
    """
    사진을 업로드하면 즉시 202(접수됨)를 반환하고
    백그라운드에서 AI 분석(품질검사 → Claude+OpenAI+YOLO → 앙상블)을 진행합니다.
    결과는 GET /analysis/{id} 로 확인하세요.
    """
    # ── 1. 파일 검증 ──────────────────────────────────────
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=400, detail="JPG, PNG, WEBP 형식만 업로드 가능합니다.")

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.MAX_IMAGE_SIZE_MB:
        raise HTTPException(
            status_code=400,
            detail=f"파일 크기가 {settings.MAX_IMAGE_SIZE_MB}MB를 초과합니다."
        )

    # ── 2. 파일 저장 ──────────────────────────────────────
    image_hash = hashlib.sha256(content).hexdigest()[:16]
    ext = Path(file.filename or "image.jpg").suffix or ".jpg"
    save_path = os.path.join(settings.UPLOAD_DIR, f"{image_hash}{ext}")

    with open(save_path, "wb") as f:
        f.write(content)

    # ── 3. 분석 레코드 생성 (pending 상태) ────────────────
    report = AnalysisReport(
        image_path=save_path,
        image_hash=image_hash,
        status="pending",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    # ── 4. 백그라운드 분석 시작 ───────────────────────────
    background_tasks.add_task(analyze_image_task, report.id)

    return report


@router.get("/{report_id}", response_model=ReportRead, summary="분석 결과 조회")
async def get_report(report_id: int, db: AsyncSession = Depends(get_db)):
    """
    분석 상태(status) 확인:
    - pending       : 대기 중
    - analyzing     : 분석 중
    - completed     : 완료
    - needs_recapture: 재촬영 필요 (summary_text에 안내 메시지 있음)
    - failed        : 오류 발생
    """
    result = await db.execute(
        select(AnalysisReport).where(AnalysisReport.id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다.")
    return report


@router.get("/{report_id}/recapture", summary="재촬영 요청 메시지 조회")
async def get_recapture_message(report_id: int, db: AsyncSession = Depends(get_db)):
    """
    status가 needs_recapture인 경우 사용자에게 보여줄 메시지를 반환합니다.
    모바일 앱에서 이 API를 호출해 팝업 메시지를 표시하세요.
    """
    result = await db.execute(
        select(AnalysisReport).where(AnalysisReport.id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다.")

    if report.status != "needs_recapture":
        return {"needs_recapture": False, "message": ""}

    return {
        "needs_recapture": True,
        "message": report.summary_text or "사진을 다시 촬영해 주세요.",
        "issue": report.error_message or "",
    }

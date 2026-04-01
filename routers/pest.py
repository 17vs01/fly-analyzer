"""
routers/pest.py - 해충 정보 조회 API
GET /pests/        → 전체 해충 목록
GET /pests/{id}    → 특정 해충 상세 정보
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database import get_db
from models.pest import Pest
from schemas.pest import PestRead, PestList

router = APIRouter(prefix="/pests", tags=["해충 정보"])


@router.get("/", response_model=PestList, summary="전체 해충 목록 조회")
async def list_pests(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Pest).order_by(Pest.name_ko))
    pests = result.scalars().all()
    return PestList(total=len(pests), items=pests)


@router.get("/{pest_id}", response_model=PestRead, summary="특정 해충 상세 조회")
async def get_pest(pest_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Pest).where(Pest.id == pest_id))
    pest = result.scalar_one_or_none()
    if not pest:
        raise HTTPException(status_code=404, detail=f"해충 ID {pest_id}를 찾을 수 없습니다.")
    return pest

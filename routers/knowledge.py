"""
routers/knowledge.py - 사용자 커스텀 지식 CRUD API
POST   /knowledge/          → 새 지식 입력 (SQLite + ChromaDB 동시 저장)
GET    /knowledge/          → 전체 지식 목록
GET    /knowledge/search    → 키워드로 지식 검색
GET    /knowledge/stats     → ChromaDB 저장 통계
GET    /knowledge/{id}      → 특정 지식 상세
PUT    /knowledge/{id}      → 지식 수정 (ChromaDB도 동시 수정)
DELETE /knowledge/{id}      → 지식 삭제 (ChromaDB도 동시 삭제)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from database import get_db
from models.knowledge import UserKnowledge
from models.pest import Pest
from schemas.knowledge import KnowledgeCreate, KnowledgeRead
from services.rag_service import rag_service
from typing import List

router = APIRouter(prefix="/knowledge", tags=["사용자 지식 (RAG)"])


@router.post("/", response_model=KnowledgeRead, status_code=201, summary="새 지식 입력")
async def create_knowledge(data: KnowledgeCreate, db: AsyncSession = Depends(get_db)):
    """
    현장에서 발견한 서식지 정보나 방역 방법을 입력합니다.
    ★ 이 데이터는 문헌 정보보다 높은 우선순위로 분석에 반영됩니다.
    SQLite DB와 ChromaDB(벡터)에 동시 저장됩니다.
    """
    # ── 1. SQLite에 저장 ──────────────────────────────────
    knowledge = UserKnowledge(**data.model_dump())
    db.add(knowledge)
    await db.commit()
    await db.refresh(knowledge)

    # ── 2. 해충 이름 조회 (pest_id로 이름 가져오기) ────────
    pest_name = data.pest_name_raw or ""
    if data.pest_id:
        result = await db.execute(select(Pest.name_ko).where(Pest.id == data.pest_id))
        pest_name = result.scalar_one_or_none() or pest_name

    # ── 3. ChromaDB에 벡터로 저장 ────────────────────────
    try:
        chroma_id = rag_service.save_knowledge(
            knowledge_id=knowledge.id,
            title=data.title,
            content=data.content,
            knowledge_type=data.knowledge_type,
            pest_name=pest_name,
            location_type=data.location_type or "",
            tags=data.tags or [],
            confidence_score=data.confidence_score,
        )
        # ChromaDB ID를 SQLite에도 기록 (수정/삭제 시 필요)
        knowledge.chroma_doc_id = chroma_id
        await db.commit()
        await db.refresh(knowledge)
    except Exception as e:
        # ChromaDB 저장 실패해도 SQLite 저장은 유지
        # (나중에 재시도 가능)
        knowledge.chroma_doc_id = None
        await db.commit()

    return knowledge


@router.get("/stats", summary="ChromaDB 저장 통계")
async def get_rag_stats():
    """현재 벡터 DB에 저장된 지식 수를 반환합니다."""
    return rag_service.get_stats()


@router.get("/search", summary="키워드로 지식 검색")
async def search_knowledge(
    query: str,
    pest_name: str = "",
    top_k: int = 5,
):
    """
    입력한 키워드와 의미적으로 유사한 지식을 검색합니다.
    (예: query="배수구 청소", pest_name="얼룩점초파리")
    """
    results = rag_service.search(query=query, pest_name=pest_name, top_k=top_k)
    return {
        "query": query,
        "pest_name": pest_name,
        "count": len(results),
        "results": [
            {
                "knowledge_id": r.knowledge_id,
                "title": r.title,
                "knowledge_type": r.knowledge_type,
                "pest_name": r.pest_name,
                "relevance_score": r.relevance_score,
                "confidence_score": r.confidence_score,
            }
            for r in results
        ],
    }


@router.get("/", response_model=List[KnowledgeRead], summary="전체 지식 목록")
async def list_knowledge(
    knowledge_type: str | None = None,
    pest_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(UserKnowledge).order_by(UserKnowledge.created_at.desc())
    if knowledge_type:
        query = query.where(UserKnowledge.knowledge_type == knowledge_type)
    if pest_id:
        query = query.where(UserKnowledge.pest_id == pest_id)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{knowledge_id}", response_model=KnowledgeRead, summary="특정 지식 조회")
async def get_knowledge(knowledge_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(UserKnowledge).where(UserKnowledge.id == knowledge_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="해당 지식을 찾을 수 없습니다.")
    return item


@router.put("/{knowledge_id}", response_model=KnowledgeRead, summary="지식 수정")
async def update_knowledge(
    knowledge_id: int, data: KnowledgeCreate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(UserKnowledge).where(UserKnowledge.id == knowledge_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="해당 지식을 찾을 수 없습니다.")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    item.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(item)

    # ── ChromaDB도 동시 수정 ──────────────────────────────
    pest_name = data.pest_name_raw or ""
    if data.pest_id:
        r = await db.execute(select(Pest.name_ko).where(Pest.id == data.pest_id))
        pest_name = r.scalar_one_or_none() or pest_name

    try:
        if item.chroma_doc_id:
            rag_service.update_knowledge(
                chroma_doc_id=item.chroma_doc_id,
                knowledge_id=item.id,
                title=data.title,
                content=data.content,
                knowledge_type=data.knowledge_type,
                pest_name=pest_name,
                location_type=data.location_type or "",
                tags=data.tags or [],
                confidence_score=data.confidence_score,
            )
    except Exception:
        pass

    return item


@router.delete("/{knowledge_id}", status_code=204, summary="지식 삭제")
async def delete_knowledge(knowledge_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(UserKnowledge).where(UserKnowledge.id == knowledge_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="해당 지식을 찾을 수 없습니다.")

    # ── ChromaDB에서도 삭제 ────────────────────────────────
    if item.chroma_doc_id:
        rag_service.delete_knowledge(item.chroma_doc_id)

    await db.delete(item)
    await db.commit()

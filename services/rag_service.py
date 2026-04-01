"""
services/rag_service.py - 사용자 지식 RAG(검색 증강 생성) 서비스

흐름:
  [사용자 지식 입력] → 텍스트를 벡터(숫자 배열)로 변환 → ChromaDB 저장
  [이미지 분석 시]  → 분석 결과(해충명+서식지)로 관련 지식 검색 → AI 프롬프트에 주입

★ 핵심 원칙: 사용자 지식(confidence=1.0)은 문헌 정보(0.5)보다 항상 우선
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

import chromadb
from chromadb.config import Settings as ChromaSettings

from config import settings

logger = logging.getLogger(__name__)

# ── ChromaDB 컬렉션 이름 상수 ──────────────────────────────────────────────────
COLLECTION_NAME = settings.CHROMA_COLLECTION_NAME  # "user_knowledge"


@dataclass
class RetrievedKnowledge:
    """검색된 지식 한 건"""
    knowledge_id: int           # SQLite DB의 UserKnowledge.id
    title: str
    content: str
    knowledge_type: str         # "habitat" | "control" | "behavior" | "other"
    pest_name: str              # 관련 해충 이름
    relevance_score: float      # 유사도 점수 (0.0~1.0, 높을수록 관련성 높음)
    confidence_score: float     # 사용자가 설정한 신뢰도


class RAGService:
    """
    ChromaDB를 사용하는 사용자 지식 검색 서비스.
    앱 전체에서 싱글톤으로 사용 (services/image_analyzer.py에서 인스턴스화)
    """

    def __init__(self):
        self._client: chromadb.PersistentClient | None = None
        self._collection = None

    def _get_collection(self):
        """ChromaDB 컬렉션 지연 로딩 (처음 호출 시 1회만 초기화)"""
        if self._collection is not None:
            return self._collection

        try:
            self._client = chromadb.PersistentClient(
                path=settings.CHROMA_PERSIST_DIR,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            # 컬렉션 없으면 자동 생성
            self._collection = self._client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},  # 코사인 유사도 사용
            )
            logger.info(f"✅ ChromaDB 컬렉션 연결: '{COLLECTION_NAME}'")
        except Exception as e:
            logger.error(f"ChromaDB 초기화 실패: {e}")
            raise

        return self._collection

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 저장 (사용자가 지식을 입력할 때)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def save_knowledge(
        self,
        knowledge_id: int,
        title: str,
        content: str,
        knowledge_type: str,
        pest_name: str = "",
        location_type: str = "",
        tags: list[str] | None = None,
        confidence_score: float = 1.0,
    ) -> str:
        """
        사용자 지식을 ChromaDB에 저장합니다.
        내부적으로 SentenceTransformer가 텍스트 → 벡터 변환을 처리합니다.

        Returns:
            chroma_doc_id: ChromaDB 문서 ID (SQLite에 저장해 추후 삭제/수정에 활용)
        """
        collection = self._get_collection()

        # 검색 품질 향상을 위해 제목 + 내용 + 태그를 하나의 문자열로 합침
        full_text = self._build_search_text(title, content, pest_name, location_type, tags)

        doc_id = f"knowledge_{knowledge_id}_{uuid.uuid4().hex[:8]}"

        collection.add(
            ids=[doc_id],
            documents=[full_text],
            metadatas=[
                {
                    "knowledge_id": knowledge_id,
                    "title": title,
                    "knowledge_type": knowledge_type,
                    "pest_name": pest_name or "",
                    "location_type": location_type or "",
                    "confidence_score": confidence_score,
                    # ★ 사용자 입력은 항상 HIGH priority
                    "priority": "high" if confidence_score >= 0.8 else "medium",
                    "tags": ",".join(tags or []),
                }
            ],
        )

        logger.info(f"✅ 지식 저장 완료 | id={knowledge_id} | doc_id={doc_id}")
        return doc_id

    def update_knowledge(
        self,
        chroma_doc_id: str,
        knowledge_id: int,
        title: str,
        content: str,
        knowledge_type: str,
        pest_name: str = "",
        location_type: str = "",
        tags: list[str] | None = None,
        confidence_score: float = 1.0,
    ) -> None:
        """기존 지식을 수정합니다 (삭제 후 재삽입)"""
        collection = self._get_collection()

        try:
            collection.delete(ids=[chroma_doc_id])
        except Exception:
            pass  # 없어도 계속 진행

        full_text = self._build_search_text(title, content, pest_name, location_type, tags)

        collection.add(
            ids=[chroma_doc_id],
            documents=[full_text],
            metadatas=[
                {
                    "knowledge_id": knowledge_id,
                    "title": title,
                    "knowledge_type": knowledge_type,
                    "pest_name": pest_name or "",
                    "location_type": location_type or "",
                    "confidence_score": confidence_score,
                    "priority": "high" if confidence_score >= 0.8 else "medium",
                    "tags": ",".join(tags or []),
                }
            ],
        )
        logger.info(f"✅ 지식 수정 완료 | doc_id={chroma_doc_id}")

    def delete_knowledge(self, chroma_doc_id: str) -> None:
        """지식을 ChromaDB에서 삭제합니다"""
        try:
            collection = self._get_collection()
            collection.delete(ids=[chroma_doc_id])
            logger.info(f"🗑️ 지식 삭제 완료 | doc_id={chroma_doc_id}")
        except Exception as e:
            logger.warning(f"ChromaDB 삭제 중 오류 (무시): {e}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 검색 (AI 분석 시 자동으로 호출)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def search(
        self,
        query: str,
        pest_name: str = "",
        top_k: int = 5,
        min_relevance: float = 0.3,
    ) -> list[RetrievedKnowledge]:
        """
        분석 결과와 관련된 사용자 지식을 검색합니다.

        Args:
            query      : 검색 쿼리 (예: "배수구 얼룩점초파리 방역")
            pest_name  : 해충 이름으로 추가 필터 (선택)
            top_k      : 최대 반환 건수
            min_relevance: 최소 유사도 (이 값보다 낮으면 제외)

        Returns:
            관련도 높은 지식 목록 (confidence_score 높은 것 우선)
        """
        try:
            collection = self._get_collection()

            if collection.count() == 0:
                return []  # 저장된 지식이 없으면 빈 리스트

            # 해충 이름이 있으면 쿼리에 포함
            full_query = f"{pest_name} {query}".strip() if pest_name else query

            results = collection.query(
                query_texts=[full_query],
                n_results=min(top_k, collection.count()),
                include=["documents", "metadatas", "distances"],
            )

            retrieved: list[RetrievedKnowledge] = []

            if not results["ids"] or not results["ids"][0]:
                return []

            for i, doc_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i]
                distance = results["distances"][0][i]

                # ChromaDB 코사인 거리(0~2) → 유사도(0~1)로 변환
                relevance = max(0.0, 1.0 - distance / 2.0)

                if relevance < min_relevance:
                    continue

                retrieved.append(
                    RetrievedKnowledge(
                        knowledge_id=int(meta.get("knowledge_id", 0)),
                        title=meta.get("title", ""),
                        content=results["documents"][0][i],
                        knowledge_type=meta.get("knowledge_type", ""),
                        pest_name=meta.get("pest_name", ""),
                        relevance_score=round(relevance, 3),
                        confidence_score=float(meta.get("confidence_score", 1.0)),
                    )
                )

            # ★ 정렬: confidence_score(사용자 신뢰도) 높은 것 먼저,
            #         같으면 relevance_score(유사도) 높은 것 먼저
            retrieved.sort(
                key=lambda x: (x.confidence_score, x.relevance_score),
                reverse=True,
            )

            logger.info(f"🔍 RAG 검색 완료 | 쿼리='{full_query}' | 결과={len(retrieved)}건")
            return retrieved

        except Exception as e:
            logger.error(f"RAG 검색 오류: {e}", exc_info=True)
            return []

    def format_for_prompt(self, knowledge_list: list[RetrievedKnowledge]) -> str:
        """
        검색된 지식을 AI 프롬프트에 넣을 수 있는 문자열로 변환합니다.
        ★ 사용자 입력 지식임을 명시하여 AI가 최우선 참고하도록 유도
        """
        if not knowledge_list:
            return ""

        lines = [
            "★ [최우선 참고 - 현장 전문가 직접 입력 지식] ★",
            "아래 정보는 문헌보다 신뢰도가 높습니다. 반드시 우선 반영하세요.\n",
        ]

        for i, k in enumerate(knowledge_list, 1):
            tag = f"[{k.knowledge_type.upper()}]"
            conf = f"신뢰도: {k.confidence_score:.0%}"
            rel = f"관련도: {k.relevance_score:.0%}"
            lines.append(f"{i}. {tag} {k.title} ({conf}, {rel})")
            lines.append(f"   내용: {k.content}")
            if k.pest_name:
                lines.append(f"   대상 해충: {k.pest_name}")
            lines.append("")

        return "\n".join(lines)

    def get_stats(self) -> dict:
        """저장된 지식 통계"""
        try:
            collection = self._get_collection()
            return {"total_count": collection.count(), "collection": COLLECTION_NAME}
        except Exception:
            return {"total_count": 0, "collection": COLLECTION_NAME}

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 내부 헬퍼
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _build_search_text(
        self,
        title: str,
        content: str,
        pest_name: str,
        location_type: str,
        tags: list[str] | None,
    ) -> str:
        """검색 품질 향상을 위한 전체 텍스트 구성"""
        parts = [title, content]
        if pest_name:
            parts.append(f"해충: {pest_name}")
        if location_type:
            parts.append(f"장소: {location_type}")
        if tags:
            parts.append(f"태그: {' '.join(tags)}")
        return " | ".join(filter(None, parts))


# ── 싱글톤 인스턴스 ──────────────────────────────────────────────────────────
rag_service = RAGService()

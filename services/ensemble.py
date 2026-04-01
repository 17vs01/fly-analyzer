"""
services/ensemble.py - 3개 AI 분석 결과 앙상블(합산) 로직

원리:
- Claude, OpenAI, YOLO가 각각 결과를 냄
- 가중치 투표로 최종 해충 종을 결정
- 신뢰도가 낮으면 재촬영 요청 플래그를 세움
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from config import settings
from .ai_providers.base import DetectedHabitat, ProviderResult

logger = logging.getLogger(__name__)


@dataclass
class EnsembleResult:
    """앙상블 최종 결과"""
    # ── 최종 해충 판정 ─────────────────────────────────────
    pest_name_ko: str               # 최종 결정된 해충 이름
    pest_confidence: float          # 최종 신뢰도

    # 후보 목록 (가중 점수 순)
    # [{"name_ko": "...", "score": 0.85, "votes": 2}, ...]
    pest_candidates: list[dict] = field(default_factory=list)

    # ── 서식지/오염원 ──────────────────────────────────────
    # 중복 제거 후 신뢰도 평균
    detected_habitats: list[dict] = field(default_factory=list)

    # ── 시각적 근거 (전체 수집) ───────────────────────────
    visual_evidence: list[str] = field(default_factory=list)

    # ── 상태 플래그 ───────────────────────────────────────
    needs_recapture: bool = False   # True면 재촬영 요청
    recapture_reason: str = ""

    # ── 각 제공자 결과 (디버깅용) ─────────────────────────
    provider_results: list[dict] = field(default_factory=list)


class EnsembleService:
    """3개 AI 결과를 가중 투표로 합산하는 서비스"""

    # 가중치: 합계 = 1.0 (config에서 조정 가능)
    WEIGHTS = {
        "claude": settings.WEIGHT_CLAUDE,   # 0.40
        "openai": settings.WEIGHT_OPENAI,   # 0.35
        "yolo":   settings.WEIGHT_YOLO,     # 0.25
    }

    def combine(self, results: list[ProviderResult]) -> EnsembleResult:
        """
        여러 AI 결과를 합산하여 EnsembleResult를 반환합니다.

        알고리즘:
        1. 각 제공자의 pest_name_ko에 가중치 × confidence 점수를 부여
        2. 점수 합계가 가장 높은 종을 최종 선택
        3. 최종 신뢰도가 임계값보다 낮으면 needs_recapture = True
        """
        successful = [r for r in results if r.success]

        if not successful:
            return EnsembleResult(
                pest_name_ko="",
                pest_confidence=0.0,
                needs_recapture=True,
                recapture_reason="모든 AI 분석에 실패했습니다. 다시 시도해 주세요.",
            )

        # ── 1. 해충 종별 가중 점수 합산 ──────────────────────
        pest_scores: dict[str, float] = defaultdict(float)
        pest_vote_count: dict[str, int] = defaultdict(int)

        for r in successful:
            weight = self.WEIGHTS.get(r.provider, 0.25)

            # 최우선 결과 (pest_name_ko가 있을 때)
            if r.pest_name_ko:
                score = weight * r.pest_confidence
                pest_scores[r.pest_name_ko] += score
                pest_vote_count[r.pest_name_ko] += 1

            # 후보 목록도 반영 (가중치의 50%로 처리)
            for candidate in r.pest_candidates:
                name = candidate.get("name_ko", "")
                conf = float(candidate.get("confidence", 0.0))
                if name and name != r.pest_name_ko:
                    pest_scores[name] += weight * conf * 0.5

        # ── 2. 최종 해충 결정 ─────────────────────────────────
        if pest_scores:
            sorted_pests = sorted(pest_scores.items(), key=lambda x: x[1], reverse=True)
            best_name, best_score = sorted_pests[0]

            # 점수를 0~1 범위 신뢰도로 정규화
            final_confidence = min(best_score, 1.0)

            candidates = [
                {
                    "name_ko": name,
                    "score": round(score, 3),
                    "votes": pest_vote_count[name],
                }
                for name, score in sorted_pests[:5]  # 상위 5개만
            ]
        else:
            best_name = ""
            final_confidence = 0.0
            candidates = []

        # ── 3. 서식지 합산 (중복 제거 + 신뢰도 평균) ─────────
        habitats = self._merge_habitats(
            [h for r in successful for h in r.detected_habitats]
        )

        # ── 4. 시각적 근거 수집 ────────────────────────────────
        evidence = []
        for r in successful:
            for e in r.visual_evidence:
                tagged = f"[{r.provider.upper()}] {e}"
                if tagged not in evidence:
                    evidence.append(tagged)

        # ── 5. 재촬영 여부 판단 ───────────────────────────────
        needs_recapture = False
        recapture_reason = ""

        if final_confidence < settings.CONFIDENCE_THRESHOLD:
            needs_recapture = True
            if not best_name:
                recapture_reason = (
                    "📸 사진에서 해충을 확인하기 어려웠어요.\n"
                    "벌레가 화면 중앙에 크게 나오도록 가까이서 다시 촬영해 주세요."
                )
            else:
                recapture_reason = (
                    f"🔍 '{best_name}'으로 추정되지만 확신도가 낮아요 ({final_confidence:.0%}).\n"
                    "더 선명한 사진으로 다시 찍어주시면 정확도가 높아져요!"
                )

        return EnsembleResult(
            pest_name_ko=best_name,
            pest_confidence=round(final_confidence, 3),
            pest_candidates=candidates,
            detected_habitats=habitats,
            visual_evidence=evidence,
            needs_recapture=needs_recapture,
            recapture_reason=recapture_reason,
            provider_results=[
                {
                    "provider": r.provider,
                    "success": r.success,
                    "pest_name_ko": r.pest_name_ko,
                    "pest_confidence": r.pest_confidence,
                    "error": r.error_message,
                }
                for r in results
            ],
        )

    def _merge_habitats(self, habitats: list[DetectedHabitat]) -> list[dict]:
        """같은 이름의 서식지를 합쳐 신뢰도 평균을 냄"""
        merged: dict[str, list[float]] = defaultdict(list)
        for h in habitats:
            if h.name_ko:
                merged[h.name_ko].append(h.confidence)

        result = [
            {
                "name_ko": name,
                "confidence": round(sum(confs) / len(confs), 3),
                "detection_count": len(confs),
            }
            for name, confs in merged.items()
        ]
        return sorted(result, key=lambda x: x["confidence"], reverse=True)

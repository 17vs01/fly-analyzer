"""
services/ai_providers/base.py - AI 분석기 공통 부모 클래스
새 AI 제공자 추가 시 이 클래스를 상속받아 analyze() 만 구현하면 됨
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DetectedHabitat:
    """이미지 배경에서 감지된 서식지/오염원"""
    name_ko: str                # 예: "배수구"
    confidence: float           # 감지 신뢰도 (0.0~1.0)
    bbox: Optional[list] = None  # 바운딩박스 [x, y, w, h] (있으면)


@dataclass
class ProviderResult:
    """각 AI 제공자의 분석 결과 (공통 형식)"""
    provider: str               # "claude" | "openai" | "yolo"
    success: bool               # 분석 성공 여부

    # ── 해충 분류 결과 ─────────────────────────────────────
    pest_name_ko: str = ""      # 예: "얼룩점초파리"
    pest_confidence: float = 0.0

    # 후보 목록 (신뢰도 순)
    # [{"name_ko": "...", "confidence": 0.8, "reason": "..."}, ...]
    pest_candidates: list = field(default_factory=list)

    # ── 서식지/오염원 감지 결과 ────────────────────────────
    detected_habitats: list[DetectedHabitat] = field(default_factory=list)

    # ── 시각적 근거 ───────────────────────────────────────
    visual_evidence: list[str] = field(default_factory=list)
    # 예: ["날개 끝 검은 점 확인", "배수구 근처에서 발견"]

    # ── 오류 정보 ─────────────────────────────────────────
    error_message: str = ""
    raw_response: str = ""      # 디버깅용 원본 응답


class BaseAnalyzer(ABC):
    """모든 AI 분석기의 추상 부모 클래스"""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """제공자 이름 (예: 'claude')"""

    @abstractmethod
    async def analyze(self, image_path: str, pest_context: dict) -> ProviderResult:
        """
        이미지를 분석하여 ProviderResult를 반환합니다.

        Args:
            image_path: 분석할 이미지 파일 경로
            pest_context: DB에서 가져온 해충 정보
                          {"pests": [{"name_ko": ..., "visual_features": ...}]}
        Returns:
            ProviderResult
        """

    def _make_error_result(self, error: str) -> ProviderResult:
        """오류 발생 시 표준 실패 결과 생성"""
        return ProviderResult(
            provider=self.provider_name,
            success=False,
            error_message=error,
        )

    def _encode_image_base64(self, image_path: str) -> str:
        """이미지 파일을 base64 문자열로 변환"""
        import base64
        with open(image_path, "rb") as f:
            return base64.standard_b64encode(f.read()).decode("utf-8")

    def _get_media_type(self, image_path: str) -> str:
        """파일 확장자로 미디어 타입 결정"""
        ext = image_path.lower().split(".")[-1]
        return {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
        }.get(ext, "image/jpeg")

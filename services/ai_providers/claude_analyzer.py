"""
services/ai_providers/claude_analyzer.py - Claude Vision API 분석기
사진 전체(벌레 + 배경 오염원)를 동시에 분석하는 멀티모달 로직
"""
from __future__ import annotations

import json
import logging

import anthropic

from config import settings
from .base import BaseAnalyzer, DetectedHabitat, ProviderResult

logger = logging.getLogger(__name__)

# ── Claude에게 보내는 분석 지시문 ──────────────────────────────────────────────
SYSTEM_PROMPT = """당신은 초파리류 해충 분류 전문가입니다.
사용자가 보내는 사진을 분석하여 아래 JSON 형식으로만 응답하세요.
다른 설명이나 마크다운 없이 순수 JSON만 출력하세요.

응답 형식:
{
  "pest_name_ko": "해충 한국어 이름 (모르면 빈 문자열)",
  "pest_confidence": 0.0~1.0 사이 신뢰도,
  "pest_candidates": [
    {"name_ko": "후보1", "confidence": 0.8, "reason": "판단 근거"},
    {"name_ko": "후보2", "confidence": 0.3, "reason": "판단 근거"}
  ],
  "detected_habitats": [
    {"name_ko": "배수구", "confidence": 0.9},
    {"name_ko": "음식물 쓰레기통", "confidence": 0.7}
  ],
  "visual_evidence": [
    "날개 끝에 검은 점 확인 (얼룩점초파리 수컷 특징)",
    "배경에 배수구 구조물 확인"
  ]
}"""


class ClaudeAnalyzer(BaseAnalyzer):
    """Claude Vision API를 사용하는 분석기"""

    @property
    def provider_name(self) -> str:
        return "claude"

    async def analyze(self, image_path: str, pest_context: dict) -> ProviderResult:
        if not settings.ANTHROPIC_API_KEY:
            return self._make_error_result("ANTHROPIC_API_KEY가 설정되지 않았습니다.")

        try:
            client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

            # 이미지를 base64로 인코딩
            image_data = self._encode_image_base64(image_path)
            media_type = self._get_media_type(image_path)

            # DB의 해충 정보를 프롬프트에 포함 (분류 정확도 향상)
            pest_list_str = self._format_pest_context(pest_context)

            user_message = f"""다음 사진을 분석해 주세요.

[분류 가능한 해충 목록]
{pest_list_str}

분석 시 주의사항:
1. 벌레 자체의 외형 특징을 먼저 확인하세요
2. 사진 배경에 있는 오염원(배수구, 음식물, 화분 등)도 함께 확인하세요
3. 불확실하면 여러 후보를 confidence 순으로 나열하세요"""

            response = client.messages.create(
                model=settings.CLAUDE_MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_data,
                                },
                            },
                            {"type": "text", "text": user_message},
                        ],
                    }
                ],
            )

            raw_text = response.content[0].text
            return self._parse_response(raw_text)

        except anthropic.APIError as e:
            logger.error(f"Claude API 오류: {e}")
            return self._make_error_result(f"Claude API 오류: {str(e)}")
        except Exception as e:
            logger.error(f"Claude 분석 중 예외: {e}", exc_info=True)
            return self._make_error_result(str(e))

    def _parse_response(self, raw_text: str) -> ProviderResult:
        """Claude JSON 응답을 ProviderResult로 변환"""
        try:
            # JSON 파싱 (백틱 마크다운이 붙어 있을 경우 제거)
            clean = raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            data = json.loads(clean)

            habitats = [
                DetectedHabitat(
                    name_ko=h.get("name_ko", ""),
                    confidence=float(h.get("confidence", 0.5)),
                )
                for h in data.get("detected_habitats", [])
            ]

            return ProviderResult(
                provider=self.provider_name,
                success=True,
                pest_name_ko=data.get("pest_name_ko", ""),
                pest_confidence=float(data.get("pest_confidence", 0.0)),
                pest_candidates=data.get("pest_candidates", []),
                detected_habitats=habitats,
                visual_evidence=data.get("visual_evidence", []),
                raw_response=raw_text,
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Claude 응답 파싱 실패: {e} | 원문: {raw_text[:200]}")
            return self._make_error_result(f"응답 파싱 실패: {e}")

    def _format_pest_context(self, pest_context: dict) -> str:
        """DB 해충 정보를 프롬프트용 문자열로 변환"""
        lines = []
        for p in pest_context.get("pests", []):
            features = ", ".join(p.get("visual_features") or [])
            lines.append(f"- {p['name_ko']} ({p.get('name_scientific', '')}): {features}")
        return "\n".join(lines) if lines else "정보 없음"

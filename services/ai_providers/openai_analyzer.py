"""
services/ai_providers/openai_analyzer.py - OpenAI GPT-4o Vision 분석기
★ 수정: AsyncOpenAI 사용 → asyncio.gather 진짜 병렬 실행
"""
from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from config import settings
from .base import BaseAnalyzer, DetectedHabitat, ProviderResult

logger = logging.getLogger(__name__)

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


class OpenAIAnalyzer(BaseAnalyzer):
    """GPT-4o Vision API를 사용하는 분석기 (비동기)"""

    @property
    def provider_name(self) -> str:
        return "openai"

    async def analyze(self, image_path: str, pest_context: dict) -> ProviderResult:
        if not settings.OPENAI_API_KEY:
            return self._make_error_result("OPENAI_API_KEY가 설정되지 않았습니다.")

        try:
            # ★ AsyncOpenAI 사용 → 이벤트 루프 안 막음
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

            image_data = self._encode_image_base64(image_path)
            media_type = self._get_media_type(image_path)
            pest_list_str = self._format_pest_context(pest_context)

            user_message = f"""다음 사진을 분석해 주세요.

[분류 가능한 해충 목록]
{pest_list_str}

분석 시 주의사항:
1. 벌레 자체의 외형 특징을 먼저 확인하세요
2. 사진 배경에 있는 오염원(배수구, 음식물, 화분 등)도 함께 확인하세요
3. 불확실하면 여러 후보를 confidence 순으로 나열하세요"""

            # ★ await 추가
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                max_tokens=1024,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{media_type};base64,{image_data}",
                                    "detail": "high",
                                },
                            },
                            {"type": "text", "text": user_message},
                        ],
                    },
                ],
            )

            raw_text = response.choices[0].message.content or ""
            return self._parse_response(raw_text)

        except Exception as e:
            logger.error(f"OpenAI 분석 중 예외: {e}", exc_info=True)
            return self._make_error_result(str(e))

    def _parse_response(self, raw_text: str) -> ProviderResult:
        try:
            clean = (
                raw_text.strip()
                .removeprefix("```json")
                .removeprefix("```")
                .removesuffix("```")
                .strip()
            )
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
            logger.warning(f"OpenAI 응답 파싱 실패: {e}")
            return self._make_error_result(f"응답 파싱 실패: {e}")

    def _format_pest_context(self, pest_context: dict) -> str:
        lines = []
        for p in pest_context.get("pests", []):
            features = ", ".join(p.get("visual_features") or [])
            lines.append(f"- {p['name_ko']} ({p.get('name_scientific', '')}): {features}")
        return "\n".join(lines) if lines else "정보 없음"

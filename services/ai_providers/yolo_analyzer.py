"""
services/ai_providers/yolo_analyzer.py - YOLOv8 로컬 모델 분석기
★ 수정: asyncio.get_event_loop().run_in_executor() 로 동기 호출 감싸기
        → asyncio.gather 에서 Claude/OpenAI와 진짜 병렬 실행 가능
"""
from __future__ import annotations

import asyncio
import logging
from functools import partial

from config import settings
from .base import BaseAnalyzer, DetectedHabitat, ProviderResult

logger = logging.getLogger(__name__)

# COCO 클래스 → 서식지 매핑 (배경 오염원 감지용)
COCO_TO_HABITAT: dict[str, str] = {
    "potted plant": "화분/식물",
    "sink":         "주방 싱크대 주변",
    "bottle":       "음식물 쓰레기통",
    "cup":          "음식물 쓰레기통",
    "bowl":         "주방 싱크대 주변",
    "banana":       "익은 과일",
    "apple":        "익은 과일",
    "orange":       "익은 과일",
    "broccoli":     "음식물 쓰레기통",
    "carrot":       "음식물 쓰레기통",
}


class YoloAnalyzer(BaseAnalyzer):
    """YOLOv8을 사용하는 로컬 분석기"""

    def __init__(self):
        self._model = None  # 지연 로딩

    @property
    def provider_name(self) -> str:
        return "yolo"

    def _load_model(self):
        """YOLOv8 모델 로드 (최초 1회만 실행)"""
        if self._model is not None:
            return
        try:
            from ultralytics import YOLO
            self._model = YOLO(settings.YOLO_MODEL_PATH)
            logger.info(f"✅ YOLO 모델 로드 완료: {settings.YOLO_MODEL_PATH}")
        except Exception as e:
            logger.error(f"YOLO 모델 로드 실패: {e}")
            self._model = None

    def _run_inference(self, image_path: str):
        """동기 YOLO 추론 (executor에서 실행되는 함수)"""
        self._load_model()
        if self._model is None:
            return None
        return self._model(image_path, conf=settings.YOLO_CONFIDENCE, verbose=False)

    async def analyze(self, image_path: str, pest_context: dict) -> ProviderResult:
        try:
            loop = asyncio.get_event_loop()
            # ★ run_in_executor: 동기 YOLO 호출을 스레드풀에서 실행
            #   → 이벤트 루프가 안 막혀서 Claude/OpenAI와 진짜 병렬 실행됨
            results = await loop.run_in_executor(
                None,
                partial(self._run_inference, image_path),
            )

            if results is None:
                return self._make_error_result("YOLO 모델을 로드할 수 없습니다.")

            return self._parse_results(results)

        except Exception as e:
            logger.error(f"YOLO 분석 중 예외: {e}", exc_info=True)
            return self._make_error_result(str(e))

    def _parse_results(self, results) -> ProviderResult:
        """YOLO 결과를 ProviderResult로 변환"""
        detected_habitats: list[DetectedHabitat] = []
        visual_evidence: list[str] = []
        found_insect = False
        best_insect_conf = 0.0

        for result in results:
            if result.boxes is None:
                continue

            for box in result.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                cls_name = result.names.get(cls_id, "")

                if cls_name in COCO_TO_HABITAT:
                    habitat_ko = COCO_TO_HABITAT[cls_name]
                    bbox = box.xyxy[0].tolist()
                    detected_habitats.append(
                        DetectedHabitat(name_ko=habitat_ko, confidence=conf, bbox=bbox)
                    )
                    visual_evidence.append(f"배경에서 '{cls_name}' 감지 (신뢰도: {conf:.0%})")

                if conf > best_insect_conf:
                    best_insect_conf = conf
                    found_insect = True

        pest_conf = best_insect_conf * 0.5 if found_insect else 0.0
        if found_insect:
            visual_evidence.append(f"이미지에서 곤충 형태 감지 (YOLO 신뢰도: {best_insect_conf:.0%})")

        return ProviderResult(
            provider=self.provider_name,
            success=True,
            pest_name_ko="",           # YOLO는 종 분류 안 함 (Claude/OpenAI 결과 신뢰)
            pest_confidence=pest_conf,
            pest_candidates=[],
            detected_habitats=detected_habitats,
            visual_evidence=visual_evidence,
        )

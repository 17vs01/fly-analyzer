"""
services/ai_providers/yolo_analyzer.py - YOLOv8 로컬 모델 분석기

역할:
- 이미지에서 곤충이 존재하는지 빠르게 감지 (바운딩박스)
- Claude/OpenAI의 교차 검증 및 위치 정보 제공
- 오프라인 환경에서도 동작 가능

학습 데이터 참고:
- 현재는 COCO 사전학습 모델 사용 (곤충 일반 감지)
- 정확도 향상: 초파리 전용 데이터셋으로 fine-tuning 필요
  → 참고: https://docs.ultralytics.com/modes/train/
"""
from __future__ import annotations

import logging
from pathlib import Path

from config import settings
from .base import BaseAnalyzer, DetectedHabitat, ProviderResult

logger = logging.getLogger(__name__)

# COCO 클래스 중 곤충/오염원과 관련된 항목
# YOLO가 감지할 수 있는 관련 클래스 ID (COCO 기준)
INSECT_RELATED_CLASSES = {
    # COCO에는 별도 초파리 클래스가 없으므로 근접 클래스 활용
    # fine-tuning 후에는 커스텀 클래스로 교체
}

# COCO 클래스 → 서식지 매핑 (배경 오염원 감지용)
COCO_TO_HABITAT: dict[str, str] = {
    "potted plant": "화분/식물",
    "sink": "주방 싱크대 주변",
    "bottle": "음식물 쓰레기통",
    "cup": "음식물 쓰레기통",
    "bowl": "주방 싱크대 주변",
    "banana": "익은 과일",
    "apple": "익은 과일",
    "orange": "익은 과일",
    "broccoli": "음식물 쓰레기통",
    "carrot": "음식물 쓰레기통",
}


class YoloAnalyzer(BaseAnalyzer):
    """YOLOv8을 사용하는 로컬 분석기"""

    def __init__(self):
        self._model = None  # 지연 로딩 (처음 분석 시에만 모델 로드)

    @property
    def provider_name(self) -> str:
        return "yolo"

    def _load_model(self):
        """YOLOv8 모델 로드 (최초 1회만 실행)"""
        if self._model is not None:
            return

        try:
            from ultralytics import YOLO
            model_path = settings.YOLO_MODEL_PATH

            # 모델 파일이 없으면 자동 다운로드
            self._model = YOLO(model_path)
            logger.info(f"✅ YOLO 모델 로드 완료: {model_path}")
        except Exception as e:
            logger.error(f"YOLO 모델 로드 실패: {e}")
            self._model = None

    async def analyze(self, image_path: str, pest_context: dict) -> ProviderResult:
        try:
            self._load_model()
            if self._model is None:
                return self._make_error_result("YOLO 모델을 로드할 수 없습니다.")

            results = self._model(
                image_path,
                conf=settings.YOLO_CONFIDENCE,
                verbose=False,
            )

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

                # ── 서식지/오염원 감지 ──────────────────────
                if cls_name in COCO_TO_HABITAT:
                    habitat_ko = COCO_TO_HABITAT[cls_name]
                    bbox = box.xyxy[0].tolist()  # [x1, y1, x2, y2]
                    detected_habitats.append(
                        DetectedHabitat(
                            name_ko=habitat_ko,
                            confidence=conf,
                            bbox=bbox,
                        )
                    )
                    visual_evidence.append(f"배경에서 '{cls_name}' 감지 (신뢰도: {conf:.0%})")

                # ── 곤충 감지 (fine-tuning 전: 일반 감지) ───
                # TODO: 초파리 전용 모델 학습 후 이 부분을 커스텀 클래스로 교체
                if conf > best_insect_conf:
                    best_insect_conf = conf
                    found_insect = True

        # YOLO는 종 분류보다 존재 감지에 집중
        # 종 이름은 Claude/OpenAI 결과를 신뢰
        pest_name = ""
        pest_conf = best_insect_conf * 0.5 if found_insect else 0.0

        if found_insect:
            visual_evidence.append(f"이미지에서 곤충 형태 감지 (YOLO 신뢰도: {best_insect_conf:.0%})")

        return ProviderResult(
            provider=self.provider_name,
            success=True,
            pest_name_ko=pest_name,
            pest_confidence=pest_conf,
            pest_candidates=[],
            detected_habitats=detected_habitats,
            visual_evidence=visual_evidence,
        )

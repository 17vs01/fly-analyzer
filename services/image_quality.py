"""
services/image_quality.py - 이미지 품질 검사기
AI 분석 전에 사진이 쓸 만한지 먼저 확인하는 관문

검사 항목:
1. 흐림 검사 (라플라시안 분산)
2. 밝기 검사 (너무 어둡거나 너무 밝음)
3. 해상도 검사 (너무 작은 사진)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from config import settings

logger = logging.getLogger(__name__)


class QualityIssue(str, Enum):
    """품질 문제 종류"""
    BLURRY = "blurry"           # 흐린 사진
    TOO_DARK = "too_dark"       # 너무 어두움
    TOO_BRIGHT = "too_bright"   # 너무 밝음 (과노출)
    TOO_SMALL = "too_small"     # 해상도 너무 낮음
    OK = "ok"                   # 이상 없음


# 사용자에게 보낼 재촬영 안내 메시지
RECAPTURE_MESSAGES: dict[QualityIssue, str] = {
    QualityIssue.BLURRY: (
        "📸 사진이 흐릿해서 분석이 어려워요!\n"
        "카메라를 벌레에 가까이 대고 초점이 맞을 때까지 잠깐 기다렸다가 촬영해 주세요."
    ),
    QualityIssue.TOO_DARK: (
        "💡 사진이 너무 어두워요!\n"
        "조명이 밝은 곳에서 촬영하거나, 스마트폰 플래시를 켜고 다시 찍어 주세요."
    ),
    QualityIssue.TOO_BRIGHT: (
        "☀️ 사진이 너무 밝아요 (과노출)!\n"
        "직사광선을 피하고 그늘진 곳에서 다시 촬영해 주세요."
    ),
    QualityIssue.TOO_SMALL: (
        "🔍 사진 해상도가 너무 낮아요!\n"
        "카메라를 벌레에 더 가까이 대고 선명하게 촬영해 주세요."
    ),
}


@dataclass
class QualityResult:
    """품질 검사 결과"""
    is_ok: bool                         # True면 분석 진행 가능
    issue: QualityIssue                 # 발견된 문제
    message: str                        # 사용자에게 보낼 메시지
    blur_score: float                   # 흐림 점수 (높을수록 선명)
    brightness: float                   # 평균 밝기 (0~255)
    width: int
    height: int


class ImageQualityChecker:
    """이미지 품질 검사기"""

    MIN_WIDTH = 300   # 최소 가로 해상도 (px)
    MIN_HEIGHT = 300  # 최소 세로 해상도 (px)
    MIN_BRIGHTNESS = 30   # 이 값보다 어두우면 너무 어두운 것
    MAX_BRIGHTNESS = 230  # 이 값보다 밝으면 과노출

    def check(self, image_path: str) -> QualityResult:
        """
        이미지 파일을 읽어 품질을 검사합니다.
        문제가 있으면 is_ok=False 와 함께 사용자 메시지를 반환합니다.
        """
        try:
            # OpenCV로 이미지 읽기
            img_bgr = cv2.imread(image_path)
            if img_bgr is None:
                raise ValueError("이미지를 읽을 수 없습니다.")

            h, w = img_bgr.shape[:2]
            gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

            blur_score = self._calc_blur_score(gray)
            brightness = float(np.mean(gray))

            logger.debug(
                f"품질 검사 | 크기:{w}x{h} | 흐림:{blur_score:.1f} | 밝기:{brightness:.1f}"
            )

            # ── 검사 1: 해상도 ──────────────────────────────
            if w < self.MIN_WIDTH or h < self.MIN_HEIGHT:
                return self._fail(QualityIssue.TOO_SMALL, blur_score, brightness, w, h)

            # ── 검사 2: 밝기 ────────────────────────────────
            if brightness < self.MIN_BRIGHTNESS:
                return self._fail(QualityIssue.TOO_DARK, blur_score, brightness, w, h)
            if brightness > self.MAX_BRIGHTNESS:
                return self._fail(QualityIssue.TOO_BRIGHT, blur_score, brightness, w, h)

            # ── 검사 3: 흐림 ────────────────────────────────
            if blur_score < settings.BLUR_THRESHOLD:
                return self._fail(QualityIssue.BLURRY, blur_score, brightness, w, h)

            # ── 모든 검사 통과 ──────────────────────────────
            return QualityResult(
                is_ok=True,
                issue=QualityIssue.OK,
                message="",
                blur_score=blur_score,
                brightness=brightness,
                width=w,
                height=h,
            )

        except Exception as e:
            logger.error(f"품질 검사 오류: {e}")
            # 오류 시 분석은 진행 (품질 검사 실패가 분석을 막으면 안 됨)
            return QualityResult(
                is_ok=True,
                issue=QualityIssue.OK,
                message="",
                blur_score=0.0,
                brightness=128.0,
                width=0,
                height=0,
            )

    def _calc_blur_score(self, gray: np.ndarray) -> float:
        """
        라플라시안 분산으로 흐림 점수 계산
        원리: 선명한 사진은 경계선(엣지)이 많아 분산이 높음
              흐린 사진은 경계선이 뭉개져 분산이 낮음
        """
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    def _fail(
        self,
        issue: QualityIssue,
        blur_score: float,
        brightness: float,
        w: int,
        h: int,
    ) -> QualityResult:
        return QualityResult(
            is_ok=False,
            issue=issue,
            message=RECAPTURE_MESSAGES[issue],
            blur_score=blur_score,
            brightness=brightness,
            width=w,
            height=h,
        )

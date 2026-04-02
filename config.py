"""
config.py - 앱 전체 설정값 모음
나중에 .env 파일로 값을 바꿔도 코드 수정 없이 동작함
"""
from pydantic_settings import BaseSettings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    # ── 앱 기본 정보 ──────────────────────────────────────
    APP_NAME: str = "초파리 방역 분석 시스템"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # ── 데이터베이스 ──────────────────────────────────────
    DATABASE_URL: str = f"sqlite+aiosqlite:///{BASE_DIR}/fly_analyzer.db"

    # ── 벡터 DB (RAG) ─────────────────────────────────────
    CHROMA_PERSIST_DIR: str = str(BASE_DIR / "chroma_store")
    CHROMA_COLLECTION_NAME: str = "user_knowledge"

    # ── AI 분석 (Claude API) ──────────────────────────────
    ANTHROPIC_API_KEY: str = ""
    # ★ 수정: claude-sonnet-4-20250514(구버전) → claude-sonnet-4-6(최신)
    CLAUDE_MODEL: str = "claude-sonnet-4-6"

    # ── AI 분석 (OpenAI API) ──────────────────────────────
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"

    # ── YOLO 로컬 모델 ────────────────────────────────────
    # 처음엔 yolov8n.pt (nano, 빠름). 정확도 높이려면 yolov8s.pt로 교체
    YOLO_MODEL_PATH: str = "yolov8n.pt"
    YOLO_CONFIDENCE: float = 0.3

    # ── 앙상블 가중치 (합계 = 1.0) ───────────────────────
    WEIGHT_CLAUDE: float = 0.40
    WEIGHT_OPENAI: float = 0.35
    WEIGHT_YOLO: float = 0.25

    # ── 이미지 저장 ───────────────────────────────────────
    UPLOAD_DIR: str = str(BASE_DIR / "uploads")
    MAX_IMAGE_SIZE_MB: int = 10

    # ── 이미지 품질 임계값 ────────────────────────────────
    # 라플라시안 분산: 이 값보다 낮으면 "흐린 사진"으로 판단
    BLUR_THRESHOLD: float = 80.0

    # ── 신뢰도 임계값 ─────────────────────────────────────
    CONFIDENCE_THRESHOLD: float = 0.6

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# 앱 전체에서 이 객체 하나만 사용
settings = Settings()

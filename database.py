"""
database.py - 데이터베이스 연결 관리
SQLite(개발) → PostgreSQL(배포) 전환 시 DATABASE_URL만 바꾸면 됨
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config import settings
import logging

logger = logging.getLogger(__name__)

# ── DB 엔진 (연결 담당) ───────────────────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,       # DEBUG=True면 SQL 쿼리를 터미널에 출력
    future=True,
)

# ── 세션 팩토리 (요청마다 DB 세션을 만들어줌) ─────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,    # commit 후에도 객체 속성 접근 가능
    autocommit=False,
    autoflush=False,
)


# ── 모든 모델의 부모 클래스 ───────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── DB 세션을 API 라우터에 주입해주는 함수 ────────────────────────────────────
async def get_db() -> AsyncSession:
    """FastAPI의 Depends()와 함께 사용하는 DB 세션 제공자"""
    from sqlalchemy.exc import SQLAlchemyError
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except SQLAlchemyError as e:
            # DB 관련 오류만 여기서 처리 (FastAPI 검증 오류는 제외)
            await session.rollback()
            logger.error(f"DB 오류: {e}")
            raise
        finally:
            await session.close()


# ── 앱 시작 시 테이블 자동 생성 ──────────────────────────────────────────────
async def init_db():
    """모든 모델 테이블을 DB에 생성 (없으면 새로 만들고, 있으면 유지)"""
    # 모든 모델을 먼저 import해야 Base.metadata에 등록됨
    from models import pest, habitat, knowledge, report  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ 데이터베이스 테이블 초기화 완료")

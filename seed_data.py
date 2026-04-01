"""
seed_data.py - DB 초기 데이터 주입
앱 처음 실행 시 한 번만 실행됨
새 해충/서식지 추가는 이 파일의 PESTS / HABITATS 리스트에 항목 추가
"""
import asyncio
import logging
from sqlalchemy import select
from database import AsyncSessionLocal, init_db
from models.pest import Pest
from models.habitat import Habitat
from models.pest import PestHabitatLink

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📌 해충 데이터 (새 종 추가 시 이 리스트에 dict 추가)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PESTS = [
    {
        "name_ko": "얼룩점초파리",
        "name_en": "Spotted Wing Drosophila",
        "name_scientific": "Drosophila suzukii",
        "body_size_mm_min": 2.0,
        "body_size_mm_max": 3.5,
        "color_pattern": "노란빛 갈색 몸통, 검은 가로줄 무늬",
        "wing_pattern": "수컷 날개 끝에 검은 점 1개 (★핵심 식별 특징)",
        "visual_features": [
            "날개 끝 검은 점(수컷)",
            "노란갈색 몸통",
            "붉은 눈",
            "투명 날개",
        ],
        "active_season": "봄~가을 (5~10월), 여름 최성기",
        "preferred_temperature": "20~25°C",
        "lifecycle_days": 12,
        "basic_control_methods": [
            "배수구 청소 및 커버 설치",
            "익은 과일 신속 제거",
            "끈끈이 트랩 설치",
            "식초 트랩 사용",
        ],
        "priority_weight": 1.0,
    },
    {
        "name_ko": "얼룩무늬등초파리",
        "name_en": "Striped Drosophila",
        "name_scientific": "Drosophila bipectinata",
        "body_size_mm_min": 2.5,
        "body_size_mm_max": 4.0,
        "color_pattern": "등 부분에 줄무늬 패턴",
        "wing_pattern": "날개에 미세한 줄무늬",
        "visual_features": [
            "등 줄무늬 패턴",
            "갈색 몸통",
            "붉은 눈",
        ],
        "active_season": "여름~초가을 (6~9월)",
        "preferred_temperature": "22~28°C",
        "lifecycle_days": 14,
        "basic_control_methods": [
            "유기물 발효 차단",
            "음식물 밀폐 보관",
            "환기 강화",
        ],
        "priority_weight": 1.0,
    },
    {
        "name_ko": "눈초파리",
        "name_en": "Eye Gnat",
        "name_scientific": "Liohippelates spp.",
        "body_size_mm_min": 1.5,
        "body_size_mm_max": 2.5,
        "color_pattern": "검회색 몸통, 광택있는 등",
        "wing_pattern": "투명, 짧은 날개",
        "visual_features": [
            "작은 체구",
            "검회색 광택 몸통",
            "큰 홑눈",
            "짧은 날개",
        ],
        "active_season": "연중 (실내), 여름 야외",
        "preferred_temperature": "15~30°C",
        "lifecycle_days": 21,
        "basic_control_methods": [
            "눈·상처 주변 위생 관리",
            "망사 방충망 설치",
            "습기 제거",
        ],
        "priority_weight": 1.0,
    },
    {
        "name_ko": "벼룩파리",
        "name_en": "Phorid Fly",
        "name_scientific": "Megaselia scalaris",
        "body_size_mm_min": 0.5,
        "body_size_mm_max": 6.0,
        "color_pattern": "황갈색~검은색",
        "wing_pattern": "날개가 크고 날개맥이 두드러짐",
        "visual_features": [
            "등 부분이 굽은 특이 자세",
            "빠른 달리기 행동",
            "날개맥 L자형",
            "황갈색 몸",
        ],
        "active_season": "연중 (실내 환경)",
        "preferred_temperature": "18~35°C",
        "lifecycle_days": 25,
        "basic_control_methods": [
            "하수구·배수관 정기 청소",
            "사체/부패물 즉시 제거",
            "바닥 틈새 실링",
        ],
        "priority_weight": 1.0,
    },
    {
        "name_ko": "과일초파리",
        "name_en": "Common Fruit Fly",
        "name_scientific": "Drosophila melanogaster",
        "body_size_mm_min": 2.0,
        "body_size_mm_max": 3.0,
        "color_pattern": "노란갈색 몸통, 가로 검은 줄",
        "wing_pattern": "투명, 날개 시맥 뚜렷",
        "visual_features": [
            "밝은 붉은색 눈 (핵심)",
            "노란갈색 몸통",
            "투명 날개",
            "작은 체구",
        ],
        "active_season": "연중 (실내), 여름 집중",
        "preferred_temperature": "18~28°C",
        "lifecycle_days": 10,
        "basic_control_methods": [
            "과일 냉장 보관",
            "쓰레기통 밀폐",
            "식초 트랩 설치",
            "주방 표면 청결 유지",
        ],
        "priority_weight": 1.0,
    },
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📌 서식지/오염원 데이터 (새 서식지 추가 시 이 리스트에 추가)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HABITATS = [
    {
        "name_ko": "배수구",
        "name_en": "Drain",
        "category": "drain",
        "description": "주방·화장실·욕실 배수구. 유기물 잔류가 많아 최다 서식지",
        "risk_level": 5,
        "visual_keywords": ["배수구", "하수구", "구멍", "그레이팅", "배관"],
        "seasonal_risk": {"spring": 3, "summer": 5, "fall": 4, "winter": 2},
        "removal_tips": ["주 1회 이상 뜨거운 물 붓기", "베이킹소다+식초 처리", "배수구 필터 커버 설치"],
    },
    {
        "name_ko": "화분/식물",
        "name_en": "Potted Plant / Soil",
        "category": "plant",
        "description": "과습한 화분 흙. 눈초파리·버섯파리 주요 서식지",
        "risk_level": 3,
        "visual_keywords": ["화분", "흙", "식물", "잎", "화초"],
        "seasonal_risk": {"spring": 4, "summer": 4, "fall": 3, "winter": 2},
        "removal_tips": ["과습 방지 (물주기 조절)", "흙 표면 모래 도포", "황토 대신 배수 좋은 흙 사용"],
    },
    {
        "name_ko": "음식물 쓰레기통",
        "name_en": "Food Waste Bin",
        "category": "waste",
        "description": "발효 중인 음식물. 모든 초파리류의 최우선 유인원",
        "risk_level": 5,
        "visual_keywords": ["쓰레기통", "음식물", "통", "봉투", "찌꺼기"],
        "seasonal_risk": {"spring": 3, "summer": 5, "fall": 4, "winter": 2},
        "removal_tips": ["밀폐형 뚜껑 사용", "하루 1회 이상 비우기", "통 안쪽 세척", "냉장 보관"],
    },
    {
        "name_ko": "익은 과일",
        "name_en": "Ripe / Overripe Fruit",
        "category": "food",
        "description": "과숙·발효 중인 과일. 과일초파리·얼룩점초파리 주요 유인원",
        "risk_level": 4,
        "visual_keywords": ["과일", "바나나", "사과", "썩은", "발효"],
        "seasonal_risk": {"spring": 2, "summer": 5, "fall": 4, "winter": 1},
        "removal_tips": ["냉장 보관", "익은 즉시 소비 또는 냉장", "비닐 밀봉"],
    },
    {
        "name_ko": "주방 싱크대 주변",
        "name_en": "Kitchen Sink Area",
        "category": "drain",
        "description": "싱크대 하부 습기와 잔류 음식물. 복합 서식 환경",
        "risk_level": 4,
        "visual_keywords": ["싱크대", "수도꼭지", "스테인리스", "주방"],
        "seasonal_risk": {"spring": 3, "summer": 5, "fall": 4, "winter": 3},
        "removal_tips": ["사용 후 물기 제거", "싱크대 하부 건조 유지", "배관 연결부 점검"],
    },
    {
        "name_ko": "퇴비/발효 물질",
        "name_en": "Compost / Fermenting Material",
        "category": "waste",
        "description": "퇴비함, 음식 발효 중인 모든 유기물",
        "risk_level": 4,
        "visual_keywords": ["퇴비", "발효", "거름", "유기물"],
        "seasonal_risk": {"spring": 4, "summer": 5, "fall": 4, "winter": 1},
        "removal_tips": ["밀폐형 퇴비통 사용", "실외 배치", "정기적 뒤집기로 발효 촉진"],
    },
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📌 해충-서식지 연결 (pest_name_ko → habitat_name_ko, 빈도)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PEST_HABITAT_LINKS = [
    # 얼룩점초파리
    {"pest": "얼룩점초파리", "habitat": "익은 과일", "frequency": 0.95, "source": "literature"},
    {"pest": "얼룩점초파리", "habitat": "배수구", "frequency": 0.6, "source": "literature"},
    {"pest": "얼룩점초파리", "habitat": "음식물 쓰레기통", "frequency": 0.8, "source": "literature"},

    # 눈초파리
    {"pest": "눈초파리", "habitat": "화분/식물", "frequency": 0.9, "source": "literature"},
    {"pest": "눈초파리", "habitat": "퇴비/발효 물질", "frequency": 0.7, "source": "literature"},

    # 벼룩파리
    {"pest": "벼룩파리", "habitat": "배수구", "frequency": 0.95, "source": "literature"},
    {"pest": "벼룩파리", "habitat": "주방 싱크대 주변", "frequency": 0.85, "source": "literature"},
    {"pest": "벼룩파리", "habitat": "음식물 쓰레기통", "frequency": 0.7, "source": "literature"},

    # 과일초파리
    {"pest": "과일초파리", "habitat": "익은 과일", "frequency": 0.98, "source": "literature"},
    {"pest": "과일초파리", "habitat": "주방 싱크대 주변", "frequency": 0.75, "source": "literature"},
    {"pest": "과일초파리", "habitat": "음식물 쓰레기통", "frequency": 0.85, "source": "literature"},

    # 얼룩무늬등초파리
    {"pest": "얼룩무늬등초파리", "habitat": "익은 과일", "frequency": 0.8, "source": "literature"},
    {"pest": "얼룩무늬등초파리", "habitat": "퇴비/발효 물질", "frequency": 0.75, "source": "literature"},
]


async def seed():
    """DB에 초기 데이터 삽입 (이미 있으면 건너뜀)"""
    await init_db()

    async with AsyncSessionLocal() as session:
        # ── 1. 해충 데이터 삽입 ─────────────────────────────────
        pest_map: dict[str, int] = {}  # name_ko → id 매핑
        for pest_data in PESTS:
            existing = await session.execute(
                select(Pest).where(Pest.name_ko == pest_data["name_ko"])
            )
            if existing.scalar_one_or_none() is None:
                pest = Pest(**pest_data)
                session.add(pest)
                await session.flush()
                pest_map[pest.name_ko] = pest.id
                logger.info(f"  ✅ 해충 추가: {pest.name_ko}")
            else:
                result = await session.execute(
                    select(Pest.id).where(Pest.name_ko == pest_data["name_ko"])
                )
                pest_map[pest_data["name_ko"]] = result.scalar_one()

        # ── 2. 서식지 데이터 삽입 ─────────────────────────────────
        habitat_map: dict[str, int] = {}  # name_ko → id 매핑
        for habitat_data in HABITATS:
            existing = await session.execute(
                select(Habitat).where(Habitat.name_ko == habitat_data["name_ko"])
            )
            if existing.scalar_one_or_none() is None:
                habitat = Habitat(**habitat_data)
                session.add(habitat)
                await session.flush()
                habitat_map[habitat.name_ko] = habitat.id
                logger.info(f"  ✅ 서식지 추가: {habitat.name_ko}")
            else:
                result = await session.execute(
                    select(Habitat.id).where(Habitat.name_ko == habitat_data["name_ko"])
                )
                habitat_map[habitat_data["name_ko"]] = result.scalar_one()

        # ── 3. 해충-서식지 연결 삽입 ─────────────────────────────
        for link_data in PEST_HABITAT_LINKS:
            pest_id = pest_map.get(link_data["pest"])
            habitat_id = habitat_map.get(link_data["habitat"])
            if not pest_id or not habitat_id:
                continue

            existing = await session.execute(
                select(PestHabitatLink).where(
                    PestHabitatLink.pest_id == pest_id,
                    PestHabitatLink.habitat_id == habitat_id,
                )
            )
            if existing.scalar_one_or_none() is None:
                link = PestHabitatLink(
                    pest_id=pest_id,
                    habitat_id=habitat_id,
                    frequency_score=link_data["frequency"],
                    source=link_data["source"],
                )
                session.add(link)

        await session.commit()
    logger.info("🎉 시드 데이터 삽입 완료!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed())

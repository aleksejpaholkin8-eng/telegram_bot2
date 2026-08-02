# ============================================
# СИДЕРЫ — ТОЛЬКО ТАРИФНАЯ МАТРИЦА
# ============================================
# Роли, правила и команды теперь загружаются через /upload_prompt.
# Здесь оставлена только критичная для работы системы тарифная матрица.

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.models import TariffFeature


async def seed_tariff_features(session: AsyncSession):
    """Загружаем или обновляем тарифную матрицу (tier-based flags)"""
    features_data = [
        # Lite
        {"tariff": "lite", "feature": "max_roles", "access": True, "limit_value": 15},
        {"tariff": "lite", "feature": "max_daily_tokens", "access": True, "limit_value": 0},
        {"tariff": "lite", "feature": "web_search", "access": False, "limit_value": 0},
        {"tariff": "lite", "feature": "byok", "access": False, "limit_value": 0},
        {"tariff": "lite", "feature": "sandbox", "access": False, "limit_value": 0},
        {"tariff": "lite", "feature": "cluster", "access": False, "limit_value": 0},
        # Pro
        {"tariff": "pro", "feature": "max_roles", "access": True, "limit_value": 35},
        {"tariff": "pro", "feature": "max_daily_tokens", "access": True, "limit_value": 5000},
        {"tariff": "pro", "feature": "web_search", "access": True, "limit_value": 50},
        {"tariff": "pro", "feature": "byok", "access": True, "limit_value": 1},
        {"tariff": "pro", "feature": "sandbox", "access": False, "limit_value": 0},
        {"tariff": "pro", "feature": "cluster", "access": False, "limit_value": 0},
        # Business
        {"tariff": "business", "feature": "max_roles", "access": True, "limit_value": 60},
        {"tariff": "business", "feature": "max_daily_tokens", "access": True, "limit_value": 999999},
        {"tariff": "business", "feature": "web_search", "access": True, "limit_value": 999},
        {"tariff": "business", "feature": "byok", "access": True, "limit_value": 5},
        {"tariff": "business", "feature": "sandbox", "access": True, "limit_value": 1},
        {"tariff": "business", "feature": "cluster", "access": True, "limit_value": 1},
    ]

    for data in features_data:
        result = await session.execute(
            select(TariffFeature).where(
                TariffFeature.tariff == data["tariff"],
                TariffFeature.feature == data["feature"]
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            existing.access = data["access"]
            existing.limit_value = data["limit_value"]
        else:
            session.add(TariffFeature(**data))
    
    await session.commit()


async def run_all_seeders(session: AsyncSession):
    """Запускает только критичные сидеры.
    Роли, правила и команды загружаются владельцем через /upload_prompt."""
    await seed_tariff_features(session)

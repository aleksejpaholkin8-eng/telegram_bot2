from typing import Tuple
from db.database import async_session
from db.models import TariffFeature, UserState
from sqlalchemy import select

async def check_feature_access(tariff: str, feature: str) -> Tuple[bool, int]:
    """
    Проверяет, доступна ли функция в тарифе.
    Возвращает: (доступно, лимит)
    """
    async with async_session() as session:
        result = await session.execute(
            select(TariffFeature).where(
                TariffFeature.tariff == tariff,
                TariffFeature.feature == feature
            )
        )
        feat = result.scalar_one_or_none()

        if not feat:
            return False, 0

        return feat.access, feat.limit_value or 0

async def check_token_limit(user_id: int, tariff: str) -> Tuple[bool, str]:
    """
    Проверяет, не исчерпан ли дневной лимит токенов.
    Возвращает: (можно_ли_использовать, сообщение_об_ошибке)
    """
    has_access, limit = await check_feature_access(tariff, "max_daily_tokens")

    if not has_access:
        return False, "AI недоступен в тарифе Lite. Обнови до Pro или Business."

    if limit == 0:
        return False, "Лимит токенов = 0"

    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == user_id)
        )
        state = result.scalar_one_or_none()

        if state and state.counters:
            used = state.counters.get("daily_tokens", 0)
            if used >= limit:
                return False, f"Дневной лимит исчерпан: {used}/{limit} токенов."

    return True, ""

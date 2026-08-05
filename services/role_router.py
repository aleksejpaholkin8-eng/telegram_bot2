# ============================================
# ROLE ROUTER — УМНЫЙ ВЫБОР РОЛЕЙ
# ============================================

import re
import logging
from typing import List
from sqlalchemy import select
from db.database import async_session
from db.models import Role, User

# ← НОВОЕ: "Дежурный пул" — роли, которые по манифесту твоего промпта должны
# быть активны ВСЕГДА, без привязки к ключевым словам в сообщении.
# Номера ролей заданы вручную, потому что в БД нет отдельного признака
# "это роль дежурного пула" — если перенумеруешь роли в промпте, поправь и здесь.
DUTY_POOL_ROLE_NUMBERS = {"2", "3", "4", "5", "23", "24", "50"}


def _role_number(role: Role) -> str:
    """Достаёт номер роли из имени вида 'Роль 12: Название роли' -> '12'"""
    m = re.match(r'^Роль\s+(\d+):', role.name)
    return m.group(1) if m else ""


async def select_roles(user_id: int, user_text: str, max_roles: int = 5) -> List[Role]:
    """
    Выбирает роли для ответа:
    1. Сначала — все роли дежурного пула, доступные пользователю по тарифу
       (они гарантированно попадают в промпт, без учёта ключевых слов).
    2. Остаток бюджета (max_roles минус размер пула) заполняется
       "специалистами" — ролями, релевантными тексту сообщения по ключевым
       словам (как и раньше).
    """
    user_text_lower = user_text.lower()
    words = set(user_text_lower.split())

    async with async_session() as session:
        # Узнаём тариф пользователя
        user_result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = user_result.scalar_one_or_none()
        tariff = user.tariff if user else "lite"

        # Проверяем, есть ли ручные настройки ролей для этого тарифа
        from db.models import RoleTariffAccess
        access_result = await session.execute(
            select(RoleTariffAccess).where(RoleTariffAccess.tariff == tariff).limit(1)
        )
        has_manual_settings = access_result.scalar_one_or_none() is not None

        if has_manual_settings:
            # Ручная настройка: берём только те роли, которые админ включил
            result = await session.execute(
                select(Role).join(
                    RoleTariffAccess,
                    Role.id == RoleTariffAccess.role_id
                ).where(
                    Role.is_active == True,
                    RoleTariffAccess.tariff == tariff,
                    RoleTariffAccess.access == True
                )
            )
            all_roles = result.scalars().all()
        else:
            # Fallback: старая логика (по tier_access)
            if tariff == "lite":
                allowed_tiers = ["lite"]
            elif tariff == "pro":
                allowed_tiers = ["lite", "pro"]
            else:
                allowed_tiers = ["lite", "pro", "business"]

            result = await session.execute(
                select(Role).where(
                    Role.is_active == True,
                    Role.tier_access.in_(allowed_tiers)
                )
            )
            all_roles = result.scalars().all()

        # --- ШАГ 1: дежурный пул (гарантированные роли) ---
        duty_pool = [r for r in all_roles if _role_number(r) in DUTY_POOL_ROLE_NUMBERS]
        duty_pool.sort(key=lambda r: int(_role_number(r)))
        # если пул почему-то больше бюджета тарифа — обрезаем его самим бюджетом,
        # чтобы не выйти за max_roles (на практике это не происходит: пул = 7,
        # а минимальный max_roles на Lite = 15)
        duty_pool = duty_pool[:max_roles]

        duty_pool_ids = {r.id for r in duty_pool}
        specialist_candidates = [r for r in all_roles if r.id not in duty_pool_ids]
        specialist_budget = max(0, max_roles - len(duty_pool))

        # --- ШАГ 2: специалисты по ключевым словам (среди оставшихся ролей) ---
        scored_roles = []

        for role in specialist_candidates:
            score = 0

            if role.keywords:
                keywords = [k.strip().lower() for k in role.keywords.split(",")]

                for kw in keywords:
                    if not kw:
                        continue
                    if len(kw) <= 2:
                        continue

                    common_words = {"как", "что", "почему", "где", "когда", "зачем", "кто"}
                    is_common = kw in common_words

                    if kw in user_text_lower:
                        if is_common:
                            score += 0.2
                        elif len(kw) >= 6:
                            score += 3
                        else:
                            score += 1

                    if kw in words:
                        score += 1

            if score > 0:
                scored_roles.append((score, role))

        scored_roles.sort(key=lambda x: x[0], reverse=True)
        specialists_selected = [role for _, role in scored_roles[:specialist_budget]]

        # --- ИТОГ: пул + специалисты ---
        selected = duty_pool + specialists_selected

        # Редкий защитный случай: ни пула (тариф режет весь дежурный пул),
        # ни совпавших специалистов — берём хоть что-то, чтобы AI не остался
        # совсем без ролей.
        if not selected and specialist_candidates:
            selected = specialist_candidates[:2]

        logging.info(
            f"RoleRouter: {len(selected)} ролей "
            f"(дежурный пул: {len(duty_pool)}, специалисты: {len(specialists_selected)}), "
            f"топ: {[r.name for r in selected[:3]]}"
        )
        return selected

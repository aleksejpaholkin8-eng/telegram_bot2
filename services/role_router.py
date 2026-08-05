import re
import logging
from typing import List
from sqlalchemy import select
from db.database import async_session
from db.models import Role, User, RoleTariffAccess

DUTY_POOL_ROLE_NUMBERS = {"2", "3", "4", "5", "23", "24", "50"}


def _role_number(role: Role) -> str:
    m = re.match(r'^Роль\s+(\d+):', role.name)
    return m.group(1) if m else ""


async def select_roles(user_id: int, user_text: str, max_roles: int = 5) -> List[Role]:
    user_text_lower = user_text.lower()
    words = set(user_text_lower.split())

    async with async_session() as session:
        user_result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = user_result.scalar_one_or_none()
        tariff = user.tariff if user else "lite"

        access_result = await session.execute(
            select(RoleTariffAccess).where(RoleTariffAccess.tariff == tariff).limit(1)
        )
        has_manual_settings = access_result.scalar_one_or_none() is not None

        if has_manual_settings:
            result = await session.execute(
                select(Role).join(
                    RoleTariffAccess, Role.id == RoleTariffAccess.role_id
                ).where(
                    Role.is_active == True,
                    RoleTariffAccess.tariff == tariff,
                    RoleTariffAccess.access == True
                )
            )
            all_roles = result.scalars().all()
        else:
            allowed_tiers = ["lite"] if tariff == "lite" else ["lite", "pro"] if tariff == "pro" else ["lite", "pro", "business"]
            result = await session.execute(
                select(Role).where(Role.is_active == True, Role.tier_access.in_(allowed_tiers))
            )
            all_roles = result.scalars().all()

        duty_pool = [r for r in all_roles if _role_number(r) in DUTY_POOL_ROLE_NUMBERS]
        duty_pool.sort(key=lambda r: int(_role_number(r)))
        duty_pool = duty_pool[:max_roles]

        duty_pool_ids = {r.id for r in duty_pool}
        specialist_candidates = [r for r in all_roles if r.id not in duty_pool_ids]
        specialist_budget = max(0, max_roles - len(duty_pool))

        scored_roles = []
        for role in specialist_candidates:
            score = 0
            if role.keywords:
                keywords = [k.strip().lower() for k in role.keywords.split(",")]
                for kw in keywords:
                    if not kw or len(kw) <= 2:
                        continue
                    common_words = {"как", "что", "почему", "где", "когда", "зачем", "кто"}
                    is_common = kw in common_words
                    if kw in user_text_lower:
                        score += 0.2 if is_common else (3 if len(kw) >= 6 else 1)
                    if kw in words:
                        score += 1
            if score > 0:
                scored_roles.append((score, role))

        scored_roles.sort(key=lambda x: x[0], reverse=True)
        specialists_selected = [role for _, role in scored_roles[:specialist_budget]]
        selected = duty_pool + specialists_selected

        if not selected and specialist_candidates:
            selected = specialist_candidates[:2]

        logging.info(
            f"RoleRouter: {len(selected)} ролей "
            f"(дежурный пул: {len(duty_pool)}, специалисты: {len(specialists_selected)}), "
            f"топ: {[r.name for r in selected[:3]]}"
        )
        return selected

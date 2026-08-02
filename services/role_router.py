# ============================================
# ROLE ROUTER — УМНЫЙ ВЫБОР РОЛЕЙ
# ============================================

import logging
from typing import List
from sqlalchemy import select
from db.database import async_session
from db.models import Role, User


async def select_roles(user_id: int, user_text: str, max_roles: int = 5) -> List[Role]:
    """
    Анализирует текст и выбирает релевантные роли.
    Теперь сначала проверяет ручные настройки админа (RoleTariffAccess),
    а если их нет — использует старую логику.
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
        
        # ← НОВОЕ: проверяем, есть ли ручные настройки ролей для этого тарифа
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
        
        # --- Дальше без изменений: scoring и выбор top-N ---
        scored_roles = []
        
        for role in all_roles:
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
            
            if role.group_name != "CORE" and score > 0:
                score += 1.5
            
            if score > 0:
                scored_roles.append((score, role))
        
        scored_roles.sort(key=lambda x: x[0], reverse=True)
        
        selected = []
        core_added = False
        
        for score, role in scored_roles:
            if len(selected) >= max_roles:
                break
            
            if role.group_name == "CORE" and not core_added:
                selected.append(role)
                core_added = True
            elif role.group_name != "CORE":
                selected.append(role)
        
        if not selected:
            for role in all_roles:
                if role.group_name == "CORE" and len(selected) < 2:
                    selected.append(role)
        
        logging.info(f"RoleRouter: {len(selected)} ролей, топ: {[r.name for r in selected[:3]]}")
        return selected

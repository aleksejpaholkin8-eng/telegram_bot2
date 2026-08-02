# ============================================
# ROLE ROUTER — ВЫБОР РОЛЕЙ ПО ЗАПРОСУ
# ============================================
# Этот файл анализирует текст пользователя и выбирает
# из базы данных 3-5 самых подходящих ролей.

import logging
from typing import List
from sqlalchemy import select
from db.database import async_session
from db.models import Role, User


async def select_roles(user_id: int, user_text: str, max_roles: int = 5) -> List[Role]:
    """
    Анализирует текст пользователя и выбирает релевантные роли.
    
    Логика:
    1. Узнаём тариф пользователя (lite/pro/business)
    2. Загружаем роли, доступные этому тарифу
    3. Считаем совпадения keywords с текстом запроса
    4. Возвращаем top-N ролей с наибольшим score
    5. Если ничего не нашли — возвращаем базовые CORE-роли
    """
    user_text_lower = user_text.lower()
    
    async with async_session() as session:
        # Узнаём тариф пользователя
        user_result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = user_result.scalar_one_or_none()
        tariff = user.tariff if user else "lite"
        
        # Определяем, какие роли доступны по тарифу
        # lite → только lite
        # pro → lite + pro
        # business → lite + pro + business
        if tariff == "lite":
            allowed_tiers = ["lite"]
        elif tariff == "pro":
            allowed_tiers = ["lite", "pro"]
        else:  # business
            allowed_tiers = ["lite", "pro", "business"]
        
        # Загружаем активные роли с подходящим tier_access
        result = await session.execute(
            select(Role).where(
                Role.is_active == True,
                Role.tier_access.in_(allowed_tiers)
            )
        )
        all_roles = result.scalars().all()
        
        # Считаем релевантность каждой роли
        scored_roles = []
        for role in all_roles:
            score = 0
            
            # Проверяем keywords
            if role.keywords:
                keywords = [k.strip().lower() for k in role.keywords.split(",")]
                for kw in keywords:
                    if kw and kw in user_text_lower:
                        score += 1  # +1 за каждое совпадение keyword
            
            # Базовые роли (CORE) получают небольшой бонус,
            # чтобы всегда были «под рукой»
            if role.group_name == "CORE" and score > 0:
                score += 0.5
            
            # Сохраняем только роли с ненулевым score
            if score > 0:
                scored_roles.append((score, role))
        
        # Сортируем: сначала самые релевантные
        scored_roles.sort(key=lambda x: x[0], reverse=True)
        
        # Берём top-N
        selected = []
        for score, role in scored_roles:
            if len(selected) < max_roles:
                selected.append(role)
        
        # Если ничего не нашли — берём первые 2-3 CORE-роли (базовые)
        if not selected:
            for role in all_roles:
                if role.group_name == "CORE" and len(selected) < 3:
                    selected.append(role)
        
        logging.info(f"RoleRouter: выбрано {len(selected)} ролей для запроса '{user_text[:50]}...'")
        return selected

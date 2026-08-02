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
    Улучшенный matching: частичное совпадение + веса + фильтрация.
    """
    user_text_lower = user_text.lower()
    words = set(user_text_lower.split())  # Разбиваем на слова
    
    async with async_session() as session:
        # Узнаём тариф
        user_result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = user_result.scalar_one_or_none()
        tariff = user.tariff if user else "lite"
        
        # Доступные тарифы
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
        
        scored_roles = []
        
        for role in all_roles:
            score = 0
            
            if role.keywords:
                keywords = [k.strip().lower() for k in role.keywords.split(",")]
                
                for kw in keywords:
                    if not kw:
                        continue
                    
                    # ПРАВИЛО 1: Слишком короткие слова (1-2 буквы) игнорируем
                    if len(kw) <= 2:
                        continue
                    
                    # ПРАВИЛО 2: Общие слова ("как", "что", "почему") — минимальный вес
                    common_words = {"как", "что", "почему", "где", "когда", "зачем", "кто"}
                    is_common = kw in common_words
                    
                    # ПРАВИЛО 3: Проверяем совпадения
                    # A) keyword полностью входит в текст (например, "корейский" в "по-корейски")
                    # B) текст входит в keyword
                    # C) keyword как отдельное слово в тексте
                    if kw in user_text_lower:
                        if is_common:
                            score += 0.2  # Общие слова почти не влияют
                        elif len(kw) >= 6:
                            score += 3    # Длинное слово — сильное совпадение
                        else:
                            score += 1    # Среднее слово
                    
                    # Отдельное слово в тексте — бонус
                    if kw in words:
                        score += 1
            
            # Бонус для релевантных ролей (не CORE)
            if role.group_name != "CORE" and score > 0:
                score += 1.5  # Специализированные роли приоритетнее
            
            if score > 0:
                scored_roles.append((score, role))
        
        # Сортируем по score (убывание)
        scored_roles.sort(key=lambda x: x[0], reverse=True)
        
        # Берём top-N, но обязательно добавляем 1 CORE-роль для стабильности
        selected = []
        core_added = False
        
        for score, role in scored_roles:
            if len(selected) >= max_roles:
                break
            
            # Если это первая CORE-роль — берём её
            if role.group_name == "CORE" and not core_added:
                selected.append(role)
                core_added = True
            elif role.group_name != "CORE":
                selected.append(role)
        
        # Если ничего не нашли — берём 2 CORE-роли
        if not selected:
            for role in all_roles:
                if role.group_name == "CORE" and len(selected) < 2:
                    selected.append(role)
        
        logging.info(f"RoleRouter: {len(selected)} ролей, топ: {[r.name for r in selected[:3]]}")
        return selected

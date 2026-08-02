# ============================================
# PROMPT BUILDER — СБОРКА СИСТЕМНОГО ПРОМПТА
# ============================================
# Собирает системный промпт из частей:
# Конституция + Роли + Паспорт + Инструкции.
# Ограничивает длину, чтобы не превысить лимит токенов.

import logging
from typing import List
from sqlalchemy import select
import tiktoken

from db.database import async_session
from db.models import Rule, UserState


def count_tokens(text: str) -> int:
    """Подсчитывает токены в тексте (приблизительно)"""
    try:
        # cl100k_base — универсальный энкодер для современных моделей
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except Exception:
        # Если tiktoken не сработал — примерная оценка: 1 токен ≈ 4 символа
        return len(text) // 4


async def build_system_prompt(user_id: int, selected_roles: List, max_tokens: int = 3000) -> str:
    """
    Собирает системный промпт из частей.
    Ограничивает общую длину max_tokens токенами.
    """
    async with async_session() as session:
        # 1. Загружаем правила (Конституция)
        rules_result = await session.execute(
            select(Rule).where(Rule.is_active == True).order_by(Rule.number)
        )
        rules = rules_result.scalars().all()
        
        # 2. Загружаем паспорт пользователя
        state_result = await session.execute(
            select(UserState).where(UserState.user_id == user_id)
        )
        user_state = state_result.scalar_one_or_none()
        
        # --- Часть 1: Заголовок ---
        header = (
            "Ты — мультиагентная система Nexus AI. "
            "Ты объединяешь в себе несколько ролей и строго следуешь Конституции."
        )
        
        # --- Часть 2: Конституция (правила) ---
        constitution = "\n\n=== КОНСТИТУЦИЯ ===\n"
        for rule in rules:
            constitution += f"{rule.number}. {rule.text}\n"
        
        # --- Часть 3: Активные роли ---
        roles_text = "\n\n=== АКТИВНЫЕ РОЛИ (действуй через призму этих ролей) ===\n"
        for i, role in enumerate(selected_roles, 1):
            roles_text += f"\n[{i}] {role.name}\n{role.prompt_text}\n"
        
        # --- Часть 4: Паспорт пользователя ---
        passport_text = ""
        if user_state and user_state.json_passport:
            passport = user_state.json_passport
            name = passport.get("name", "неизвестно")
            goal = passport.get("goal", "не указана")
            passport_text = (
                f"\n\n=== ПАСПОРТ ПОЛЬЗОВАТЕЛЯ ===\n"
                f"Имя: {name}\n"
                f"Цель: {goal}\n"
                f"Учитывай это при ответе."
            )
        
        # --- Часть 5: Инструкции по формату ---
        footer = (
            "\n\n=== ИНСТРУКЦИИ ПО ФОРМАТУ ОТВЕТА ===\n"
            "1. Отвечай на русском языке, если пользователь пишет по-русски.\n"
            "2. Будь кратким и по существу (1-3 абзаца).\n"
            "3. Если не знаешь ответ — честно скажи об этом.\n"
            "4. НЕ выдумывай факты о себе (название модели, параметры, создатель).\n"
            "5. Ссылайся на активные роли при ответе (например: «Как Архитектор, я рекомендую...»)."
        )
        
        # Собираем полный промпт
        full_prompt = header + constitution + roles_text + passport_text + footer
        
        # Проверяем длину
        current_tokens = count_tokens(full_prompt)
        logging.info(f"PromptBuilder: промпт собран, {current_tokens} токенов")
        
        # Если слишком длинный — обрезаем
        if current_tokens > max_tokens:
            logging.warning(f"Промпт слишком длинный ({current_tokens}), обрезаем...")
            
            # Убираем паспорт и footer, оставляем только header + constitution + роли
            full_prompt = header + constitution + roles_text
            
            current_tokens = count_tokens(full_prompt)
            if current_tokens > max_tokens:
                # Если всё ещё длинно — обрезаем тексты ролей
                roles_short = "\n\n=== АКТИВНЫЕ РОЛИ ===\n"
                for i, role in enumerate(selected_roles[:2], 1):
                    short_text = role.prompt_text[:300] + "..." if len(role.prompt_text) > 300 else role.prompt_text
                    roles_short += f"\n[{i}] {role.name}\n{short_text}\n"
                
                full_prompt = header + constitution + roles_short
        
        return full_prompt

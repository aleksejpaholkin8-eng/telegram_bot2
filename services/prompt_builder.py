import logging
from typing import List
from sqlalchemy import select
import tiktoken

from db.database import async_session
from db.models import Rule, UserState


def count_tokens(text: str) -> int:
    try:
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except Exception:
        return len(text) // 4


async def build_system_prompt(user_id: int, selected_roles: List, max_tokens: int = 3000) -> str:
    async with async_session() as session:
        rules_result = await session.execute(
            select(Rule).where(Rule.is_active == True).order_by(Rule.number)
        )
        rules = rules_result.scalars().all()

        state_result = await session.execute(
            select(UserState).where(UserState.user_id == user_id)
        )
        user_state = state_result.scalar_one_or_none()

    header = (
        "Ты — мультиагентная система Nexus AI. "
        "Ты ОДНОВРЕМЕННО воплощаешь ВСЕ перечисленные ниже роли. "
        "Комбинируй их компетенции синергетически — не выбирай одну."
    )

    constitution = "\n\n=== КОНСТИТУЦИЯ ===\n"
    for rule in rules:
        constitution += f"{rule.number}. {rule.text}\n"

    roles_text = "\n\n=== АКТИВНЫЕ РОЛИ (используй ВСЕХ сразу) ===\n"
    for i, role in enumerate(selected_roles, 1):
        roles_text += f"\n[{i}] {role.name}\n{role.prompt_text}\n"
    roles_text += (
        "\n---\n"
        "ИНСТРУКЦИЯ: В ответе объединяй компетенции ВСЕХ активных ролей. "
        "Не отвечай только от лица одной роли. "
        "Например, если активированы Программист и Архитектор — "
        "пиши код И объясняй архитектуру."
    )

    passport_text = ""
    if user_state and user_state.json_passport:
        passport = user_state.json_passport
        name = passport.get("name", "неизвестно")
        goal = passport.get("goal", "не указана")
        passport_text = (
            f"\n\n=== ПАСПОРТ ПОЛЬЗОВАТЕЛЯ ===\n"
            f"Имя: {name}\n"
            f"Цель: {goal}\n"
            f"Адаптируй ответ под этого человека."
        )

    footer = (
        "\n\n=== ФОРМАТ ОТВЕТА ===\n"
        "1. Отвечай на русском.\n"
        "2. Будь кратким (1-3 абзаца).\n"
        "3. НЕ выдумывай факты о себе (модель, параметры).\n"
        "4. В начале ответа КРАТКО укажи, через какие роли думаешь "
        "(1 фраза: «Через призму Программиста + Архитектора...»)."
    )

    full_prompt = header + constitution + roles_text + passport_text + footer
    current_tokens = count_tokens(full_prompt)
    logging.info(f"PromptBuilder: {current_tokens} токенов")

    if current_tokens > max_tokens:
        logging.warning(f"Обрезаем промпт ({current_tokens} токенов)")
        full_prompt = header + constitution + roles_text
        if count_tokens(full_prompt) > max_tokens:
            roles_short = "\n\n=== АКТИВНЫЕ РОЛИ ===\n"
            for i, role in enumerate(selected_roles[:2], 1):
                short = role.prompt_text[:250] + "..." if len(role.prompt_text) > 250 else role.prompt_text
                roles_short += f"\n[{i}] {role.name}\n{short}\n"
            full_prompt = header + constitution + roles_short

    return full_prompt

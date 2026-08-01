# ============================================
# СЕРВИС ДЛЯ РАБОТЫ С AI (LLM)
# ============================================

import os
import logging
from typing import Optional

from litellm import acompletion

from db.database import async_session
from db.models import User, UserApiKey, TariffFeature
from sqlalchemy import select
from services.encryption import decrypt_key

logger = logging.getLogger(__name__)


async def check_llm_access(user_id: int) -> tuple[bool, int]:
    """
    Проверяет, есть ли у пользователя доступ к AI.
    Возвращает: (доступен_ли, лимит_токенов)
    """
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            return False, 0
        
        # Смотрим лимит токенов в тарифе
        result2 = await session.execute(
            select(TariffFeature).where(
                TariffFeature.tariff == user.tariff,
                TariffFeature.feature == "max_daily_tokens"
            )
        )
        feature = result2.scalar_one_or_none()
        if not feature:
            return False, 0
        
        # Если лимит 0 — значит LLM недоступен (Lite)
        return feature.limit_value > 0, feature.limit_value


async def get_api_key(user_id: int, provider: str = "xai") -> Optional[str]:
    """
    Возвращает API-ключ для запроса к AI.
    Сначала ищет BYOK (ключ пользователя), потом owner-ключ из Railway.
    """
    # 1. Проверяем BYOK пользователя
    async with async_session() as session:
        result = await session.execute(
            select(UserApiKey).where(
                UserApiKey.user_id == user_id,
                UserApiKey.provider == provider
            )
        )
        user_key = result.scalar_one_or_none()
        if user_key:
            return decrypt_key(user_key.key_encrypted)
    
    # 2. Проверяем owner-ключ из переменных окружения
    owner_keys = {
        "xai": os.getenv("XAI_API_KEY"),
        "deepseek": os.getenv("DEEPSEEK_API_KEY"),
        "gemini": os.getenv("GEMINI_API_KEY"),
        "openai": os.getenv("OPENAI_API_KEY"),
        "anthropic": os.getenv("ANTHROPIC_API_KEY"),
    }
    
    return owner_keys.get(provider)


async def ask_llm(user_id: int, user_message: str, system_prompt: str = "") -> str:
    """
    Отправляет вопрос в AI и возвращает ответ.
    Автоматически проверяет тариф и выбирает API-ключ.
    """
    # Проверяем доступ
    has_access, limit = await check_llm_access(user_id)
    if not has_access:
        return (
            "🚫 <b>Доступ запрещён</b>\n\n"
            "В вашем тарифе <b>Lite</b> нет доступа к AI-моделям.\n"
            "Обновите тариф до <b>Pro</b> или <b>Business</b>."
        )
    
    # Получаем API-ключ
    api_key = await get_api_key(user_id, "xai")
    if not api_key:
        return (
            "⚠️ <b>API-ключ не настроен</b>\n\n"
            "Администратору нужно добавить XAI_API_KEY в Railway Variables,\n"
            "или используйте /setkey чтобы добавить свой ключ (BYOK)."
        )
    
    # Отправляем запрос в Groq (бесплатная модель Llama 3.1)
    try:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})
        
        response = await acompletion(
            model="groq/llama-3.1-8b-instant",
            messages=messages,
            api_key=api_key,
            max_tokens=1000,
            temperature=0.7
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        logger.error(f"LLM error: {e}")
        return f"❌ Ошибка при обращении к AI:\n<code>{str(e)[:300]}</code>"

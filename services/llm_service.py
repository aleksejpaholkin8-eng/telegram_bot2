# ============================================
# СЕРВИС РАБОТЫ С AI (LiteLLM)
# ============================================

import logging
from typing import Tuple

try:
    import litellm
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    logging.warning("LiteLLM не установлен")

from config.settings import settings
from db.database import async_session
from db.models import UserApiKey
from sqlalchemy import select


# Настройка LiteLLM
if LITELLM_AVAILABLE:
    litellm.drop_params = True  # Игнорировать неподдерживаемые параметры


async def get_api_key(user_id: int, provider: str = "groq") -> Tuple[str, str]:
    """
    Находит API-ключ для пользователя.
    Сначала проверяет BYOK (ключ пользователя), потом owner (ключ владельца).
    
    Возвращает: (ключ, источник)
    Источник: "byok", "owner", "none"
    """
    # 1. Проверяем BYOK (ключ пользователя)
    async with async_session() as session:
        result = await session.execute(
            select(UserApiKey).where(
                UserApiKey.user_id == user_id,
                UserApiKey.provider == provider
            )
        )
        byok = result.scalar_one_or_none()
        
        if byok:
            import base64
            try:
                # Расшифровываем (пока просто base64, в проде — нормальное шифрование)
                key = base64.b64decode(byok.key_encrypted.encode()).decode()
                if key:
                    return key, "byok"
            except Exception:
                pass  # Если расшифровка не удалась — идём дальше
    
    # 2. Проверяем owner-ключ из переменных окружения Railway
    owner_keys = {
        "groq": settings.groq_api_key,
        "deepseek": settings.deepseek_api_key,
        "gemini": settings.gemini_api_key,
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
    }
    
    key = owner_keys.get(provider, "")
    if key:
        return key, "owner"
    
    # 3. Ничего не нашли
    return "", "none"


async def ask_llm(
    prompt: str,
    user_id: int,
    model: str = "groq/llama-3.1-8b-instant",
    system_prompt: str = "",
    max_tokens: int = 1000
) -> Tuple[str, bool]:
    """
    Отправляет запрос к AI-модели через LiteLLM.
    
    prompt — вопрос пользователя
    system_prompt — инструкция для AI (кто он и как отвечать)
    
    Возвращает: (ответ, успешно_ли)
    """
    if not LITELLM_AVAILABLE:
        return "❌ Ошибка: LiteLLM не установлен", False
    
    # Получаем ключ
    api_key, source = await get_api_key(user_id, provider="groq")
    
    if not api_key:
        return (
            "🔑 Нет доступного API-ключа.\n\n"
            "Варианты:\n"
            "1. Владелец бота ещё не добавил ключ в настройки Railway\n"
            "2. Добавь свой ключ через команду /setkey (BYOK)",
            False
        )
    
    # Формируем сообщения для AI
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    # Отправляем запрос
    try:
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            api_key=api_key,
            max_tokens=max_tokens,
            temperature=0.7,
        )
        
        answer = response.choices[0].message.content
        return answer, True
        
    except Exception as e:
        logging.error(f"Ошибка LLM: {e}")
        return f"❌ Ошибка при обращении к AI:\n\n{str(e)[:300]}", False

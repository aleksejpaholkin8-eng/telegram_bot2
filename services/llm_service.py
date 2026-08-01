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


if LITELLM_AVAILABLE:
    litellm.drop_params = True


async def get_api_key(user_id: int, provider: str = "xai") -> Tuple[str, str]:
    """
    Находит API-ключ для пользователя.
    BYOK → owner → none
    """
    # 1. Проверяем BYOK
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
                key = base64.b64decode(byok.key_encrypted.encode()).decode()
                if key:
                    return key, "byok"
            except Exception:
                pass
    
    # 2. Проверяем owner-ключ
    owner_keys = {
        "groq": settings.groq_api_key,
        "xai": settings.xai_api_key,
        "deepseek": settings.deepseek_api_key,
        "gemini": settings.gemini_api_key,
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
    }
    
    key = owner_keys.get(provider, "")
    if key:
        return key, "owner"
    
    return "", "none"


async def ask_llm(
    prompt: str,
    user_id: int,
    model: str = "groq/llama-3.3-70b-versatile",
    system_prompt: str = "",
    max_tokens: int = 1000
) -> Tuple[str, bool]:
    """
    Отправляет запрос к AI-модели.
    По умолчанию используем xAI (Grok).
    """
    if not LITELLM_AVAILABLE:
        return "❌ LiteLLM не установлен", False
    
    # Определяем провайдера из названия модели (xai/... или groq/...)
    provider = model.split("/")[0] if "/" in model else "xai"
    
    api_key, source = await get_api_key(user_id, provider=provider)
    
    if not api_key:
        return (
            "🔑 Нет API-ключа.\n\n"
            "Варианты:\n"
            "1. Владелец ещё не добавил XAI_API_KEY в Railway\n"
            "2. Добавь свой ключ: /setkey",
            False
        )
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
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
        return f"❌ Ошибка AI:\n\n{str(e)[:300]}", False

# ============================================
# НАСТРОЙКИ БОТА
# ============================================

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Все настройки читаются из переменных окружения Railway.
    Если переменной нет — используется значение по умолчанию.
    """
    # Telegram
    bot_token: str = os.getenv("BOT_TOKEN", "")
    
    # Владелец бота (твой Telegram ID)
    owner_id: int = int(os.getenv("OWNER_ID", "0"))  # ← ДОБАВЬ ЭТУ СТРОКУ
    
    # База данных (Railway добавит DATABASE_URL автоматически)
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bot.db")
    
    # Режим работы
    bot_mode: str = os.getenv("BOT_MODE", "polling")
    
    # Тариф по умолчанию для новых пользователей
    default_tariff: str = os.getenv("DEFAULT_TARIFF", "lite")
    
    # API-ключи провайдеров (owner)
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    xai_api_key: str = os.getenv("XAI_API_KEY", "")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")


# Создаём один объект настроек
settings = Settings()

# ============================================
# ГЛАВНЫЙ ФАЙЛ БОТА (ЭТАП 2 — БАЗА ДАННЫХ)
# ============================================

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import router
from db.database import init_db, async_session
from db.seeders import run_all_seeders

# Включаем логи
logging.basicConfig(level=logging.INFO)

# Читаем токен
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ ОШИБКА: BOT_TOKEN не найден!")

# Создаём бота
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

# Хранилище состояний (пока в памяти, позже перейдём на Redis/БД)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Подключаем обработчики
dp.include_router(router)


async def on_startup():
    """
    Эта функция вызывается при запуске бота.
    Создаёт таблицы в БД и загружает начальные данные.
    """
    logging.info("🔄 Инициализация базы данных...")
    await init_db()  # Создаём таблицы
    
    # Загружаем начальные данные (роли, правила, команды, тарифы)
    async with async_session() as session:
        await run_all_seeders(session)
    
    logging.info("✅ База данных готова. Роли, правила и тарифы загружены.")


async def main() -> None:
    # Вызываем стартовую настройку
    await on_startup()
    
    # Удаляем старые вебхуки и начинаем polling
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

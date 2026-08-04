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

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ ОШИБКА: BOT_TOKEN не найден!")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

storage = MemoryStorage()
dp = Dispatcher(storage=storage)

dp.include_router(router)

async def on_startup():
    """
    Эта функция вызывается при запуске бота.
    Создаёт таблицы в БД и загружает начальные данные.
    """
    logging.info("🔄 Инициализация базы данных...")
    await init_db()

    async with async_session() as session:
        await run_all_seeders(session)
    
    logging.info("✅ База данных готова. Роли, правила и тарифы загружены.")

async def main() -> None:

    await on_startup()

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

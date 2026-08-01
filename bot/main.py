# ============================================
# ГЛАВНЫЙ ФАЙЛ БОТА (ЭТАП 1 — FSM + КОМАНДЫ)
# ============================================

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import router

# Включаем логи — видно в Railway
logging.basicConfig(level=logging.INFO)

# Читаем токен из переменных Railway
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ ОШИБКА: BOT_TOKEN не найден! Добавь токен в переменные окружения Railway.")

# Создаём бота
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

# Создаём хранилище состояний в памяти
# (при перезапуске Railway диалоги сбросятся — это нормально для демо)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Подключаем все обработчики из handlers.py
dp.include_router(router)

# Запуск
async def main() -> None:
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

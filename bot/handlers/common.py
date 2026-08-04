from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from bot.states import UserRegistration, ByokInput
from db.database import async_session
from db.models import User, UserState, UserApiKey
from services.encryption import encrypt_key
from config.settings import settings

router = Router()

async def get_or_create_user(message: types.Message):
    """
    Находит пользователя в БД или создаёт нового.
    Тариф 'lite' по умолчанию.
    """
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
                tariff="lite"
            )
            session.add(user)
            await session.commit()

        return user

@router.message(Command(commands="start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()

    user = await get_or_create_user(message)

    if message.from_user.id == settings.owner_id:
        admin_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🔧 Админ-меню")]],
            resize_keyboard=True
        )

        await message.answer(
            f"👋 <b>Привет, владелец!</b>\n\n"
            f"🎫 Твой тариф: <b>{user.tariff.upper()}</b>\n\n"
            f"📋 Команды:\n"
            f"/start — начало\n"
            f"/help — справка\n"
            f"/system — <b>главное меню</b> (треки, фокус, прогресс)\n"
            f"/register — регистрация\n"
            f"/roles — доступные роли\n"
            f"/commands — доступные команды\n"
            f"/setkey — добавить свой API-ключ (BYOK)\n"
            f"/admin — настройка тарифов\n"
            f"/upload_prompt — загрузить промпт\n"
            f"/settariff — сменить свой тариф\n\n"
            f"💡 Просто напиши сообщение — и я отвечу через AI.",
            reply_markup=admin_kb
        )
        return

    user_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🎛 Меню")]],
        resize_keyboard=True
    )

    await message.answer(
        f"👋 <b>Привет, {user.first_name or 'друг'}!</b>\n\n"
        f"🎫 Твой тариф: <b>{user.tariff.upper()}</b>\n\n"
        f"📋 Команды:\n"
        f"/start — начало\n"
        f"/help — справка\n"
        f"/system — <b>главное меню</b> (треки, фокус, прогресс)\n"
        f"/register — регистрация\n"
        f"/roles — доступные роли\n"
        f"/commands — доступные команды\n"
        f"/setkey — добавить свой API-ключ (BYOK)\n\n"
        f"💡 Просто напиши сообщение — и я отвечу через AI (если тариф позволяет).",
        reply_markup=user_kb
    )

@router.message(Command(commands="help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 <b>Справка</b>\n\n"
        "🎛 <b>Главное меню:</b> /system\n\n"
        "📋 <b>Команды:</b>\n"
        "• /start — перезапустить\n"
        "• /help — это сообщение\n"
        "• /system — управление треками, фокус, прогресс (кнопки)\n"
        "• /register — сохранить имя и цель\n"
        "• /roles — показать роли твоего тарифа\n"
        "• /commands — список системных команд\n"
        "• /setkey — ввести свой API-ключ (BYOK)\n"
        "• /search [запрос] — поиск в интернете (Pro/Business)\n"
        "• /searchai [запрос] — поиск + ответ AI (Pro/Business)\n\n"
        "🎫 <b>Тарифы:</b>\n"
        "🆓 Lite — команды и эхо, без AI\n"
        "⚡ Pro — AI через ключ владельца или свой (BYOK)\n"
        "💎 Business — максимум ролей и функций"
    )

@router.message(Command(commands="register"))
async def cmd_register(message: types.Message, state: FSMContext):
    await state.set_state(UserRegistration.waiting_for_name)
    await message.answer(
        "📝 <b>Регистрация</b>\n\n"
        "Шаг 1 из 3\n"
        "Как тебя зовут?"
    )

@router.message(UserRegistration.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(UserRegistration.waiting_for_goal)
    await message.answer(
        f"Приятно познакомиться, <b>{message.text}</b>!\n\n"
        f"Шаг 2 из 3\nКакая твоя главная цель?"
    )

@router.message(UserRegistration.waiting_for_goal)
async def process_goal(message: types.Message, state: FSMContext):
    await state.update_data(goal=message.text)
    data = await state.get_data()
    await state.set_state(UserRegistration.waiting_for_confirm)
    await message.answer(
        f"📋 <b>Проверь данные:</b>\n\n"
        f"👤 Имя: {data['name']}\n"
        f"🎯 Цель: {data['goal']}\n\n"
        f"Шаг 3 из 3. Всё верно? Напиши <b>да</b> или <b>нет</b>."
    )

@router.message(UserRegistration.waiting_for_confirm, F.text.lower() == "да")
async def process_confirm_yes(message: types.Message, state: FSMContext):
    data = await state.get_data()

    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == message.from_user.id)
        )
        us = result.scalar_one_or_none()

        if not us:
            us = UserState(
                user_id=message.from_user.id,
                json_passport={"name": data['name'], "goal": data['goal']}
            )
            session.add(us)
        else:
            us.json_passport = {"name": data['name'], "goal": data['goal']}

        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ <b>Регистрация завершена!</b>\n\n"
        f"👤 Имя: {data['name']}\n"
        f"🎯 Цель: {data['goal']}\n\n"
        f"💾 Данные сохранены в базу данных."
    )

@router.message(UserRegistration.waiting_for_confirm, F.text.lower() == "нет")
async def process_confirm_no(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Регистрация отменена. Напиши /register, чтобы начать заново.")

@router.message(UserRegistration.waiting_for_confirm)
async def process_confirm_invalid(message: types.Message):
    await message.answer("Не понял. Напиши <b>да</b> или <b>нет</b>.")

@router.message(Command(commands="setkey"))
async def cmd_setkey(message: types.Message, state: FSMContext):
    await state.set_state(ByokInput.waiting_for_key)
    await message.answer(
        "🔑 <b>Ввод API-ключа (BYOK)</b>\n\n"
        "Отправь свой ключ в следующем сообщении.\n"
        "Поддерживаются:\n"
        "• xAI (Grok): <code>xai-...</code>\n"
        "• Groq: <code>gsk_...</code>\n\n"
        "⚠️ Ключ будет сохранён в зашифрованном виде.\n"
        "Для отмены напиши /start."
    )

@router.message(ByokInput.waiting_for_key)
async def process_byok_key(message: types.Message, state: FSMContext):
    key = message.text.strip()

    if key.startswith("xai-"):
        provider = "xai"
    elif key.startswith("gsk_"):
        provider = "groq"
    else:
        await message.answer(
            "❌ Неизвестный формат ключа.\n"
            "Поддерживаются:\n"
            "• xAI: <code>xai-...</code>\n"
            "• Groq: <code>gsk_...</code>\n\n"
            "Попробуй снова или /start для отмены."
        )
        return

    try:
        encrypted = encrypt_key(key)
    except ValueError as e:
        await message.answer(
            f"❌ <b>Ошибка шифрования:</b>\n\n"
            f"{str(e)}\n\n"
            f"Администратору нужно добавить ENCRYPTION_KEY в переменные окружения."
        )
        await state.clear()
        return

    async with async_session() as session:
        result = await session.execute(
            select(UserApiKey).where(
                UserApiKey.user_id == message.from_user.id,
                UserApiKey.provider == provider
            )
        )
        old = result.scalar_one_or_none()
        if old:
            await session.delete(old)

        new_key = UserApiKey(
            user_id=message.from_user.id,
            provider=provider,
            key_encrypted=encrypted
        )
        session.add(new_key)
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ <b>Ключ {provider.upper()} сохранён!</b>\n\n"
        f"Теперь ты используешь BYOK-режим.\n"
        f"Расходы на токены — на твоём счету."
    )

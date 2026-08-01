# ============================================
# ОБРАБОТЧИКИ (ЭТАП 3 — AI + ТАРИФЫ + BYOK)
# ============================================

import base64

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.states import UserRegistration, ByokInput
from db.database import async_session
from db.models import User, Role, Command as CommandModel, UserState, UserApiKey
from sqlalchemy import select

from services.llm_service import ask_llm, get_api_key
from services.tariff_service import check_token_limit

router = Router()


# ============ ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ============

async def get_or_create_user(message: types.Message):
    """Находит или создаёт пользователя в БД"""
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


# ============ КОМАНДЫ ============

@router.message(Command(commands="start"))
async def cmd_start(message: types.Message):
    user = await get_or_create_user(message)
    await message.answer(
        f"👋 <b>Привет, {user.first_name or 'друг'}!</b>\n\n"
        f"🎫 Твой тариф: <b>{user.tariff.upper()}</b>\n\n"
        f"📋 Команды:\n"
        f"/start — начало\n"
        f"/help — справка\n"
        f"/register — регистрация\n"
        f"/roles — доступные роли\n"
        f"/commands — доступные команды\n"
        f"/setkey — добавить свой API-ключ (BYOK)\n\n"
        f"💡 Просто напиши сообщение — и я отвечу через AI (если тариф позволяет)."
    )


@router.message(Command(commands="help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 <b>Справка</b>\n\n"
        "• /start — перезапустить\n"
        "• /help — это сообщение\n"
        "• /register — сохранить имя и цель в базу\n"
        "• /roles — показать роли твоего тарифа\n"
        "• /commands — показать команды\n"
        "• /setkey — ввести свой API-ключ Groq (BYOK)\n\n"
        "🎫 Тарифы:\n"
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


@router.message(Command(commands="roles"))
async def cmd_roles(message: types.Message):
    user = await get_or_create_user(message)
    async with async_session() as session:
        result = await session.execute(
            select(Role).where(
                Role.is_active == True,
                Role.tier_access.in_(["lite", user.tariff])
            )
        )
        roles = result.scalars().all()
        
        text = f"🎭 <b>Роли (тариф: {user.tariff.upper()}):</b>\n\n"
        for role in roles:
            icon = "🆓" if role.tier_access == "lite" else "💎"
            text += f"{icon} <b>{role.name}</b>\n"
            text += f"   🔑 {role.keywords}\n\n"
        text += f"📊 Всего ролей: {len(roles)}"
        await message.answer(text)


@router.message(Command(commands="commands"))
async def cmd_commands(message: types.Message):
    user = await get_or_create_user(message)
    async with async_session() as session:
        result = await session.execute(
            select(CommandModel).where(
                CommandModel.tier_access.in_(["lite", user.tariff])
            )
        )
        commands = result.scalars().all()
        
        text = f"⌨️ <b>Команды (тариф: {user.tariff.upper()}):</b>\n\n"
        for cmd in commands:
            icon = "✅" if cmd.tier_access == "lite" else "🔒"
            text += f"{icon} <b>{cmd.name}</b> — {cmd.description}\n"
        await message.answer(text)


# ============ FSM: РЕГИСТРАЦИЯ ============

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


# ============ FSM: ВВОД КЛЮЧА BYOK ============

@router.message(ByokInput.waiting_for_key)
async def process_byok_key(message: types.Message, state: FSMContext):
    key = message.text.strip()
    
    # Определяем провайдера по формату ключа
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
    
    # Шифруем
    encrypted = base64.b64encode(key.encode()).decode()
    
    async with async_session() as session:
        # Удаляем старый ключ этого провайдера
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


# ============ УМНЫЙ ОБРАБОТЧИК (AI ИЛИ ЭХО) ============

@router.message()
async def smart_handler(message: types.Message):
    """
    Главный обработчик сообщений.
    Lite → эхо
    Pro/Business → AI (если есть ключ и лимит не исчерпан)
    """
    user = await get_or_create_user(message)
    
    # --- РЕЖИМ LITE: без AI ---
    if user.tariff == "lite":
        await message.answer(
            f"🤖 <b>Режим LITE</b>\n\n"
            f"Вы написали: {message.text}\n\n"
            f"В этом тарифе AI недоступен.\n"
            f"Обнови до Pro, чтобы получить умные ответы.\n\n"
            f"💡 Команды: /start /help /register /roles /commands /setkey"
        )
        return
    
    # --- РЕЖИМ PRO/BUSINESS: проверяем лимит ---
    has_access, limit_msg = await check_token_limit(message.from_user.id, user.tariff)
    if not has_access:
        await message.answer(
            f"⛔ <b>Лимит исчерпан</b>\n\n{limit_msg}\n\n"
            f"Вы написали: {message.text}"
        )
        return
    
    # --- Проверяем наличие ключа ---
    api_key, source = await get_api_key(message.from_user.id, "groq")
    if not api_key:
        await message.answer(
            f"🔑 <b>Нет API-ключа</b>\n\n"
            f"Варианты:\n"
            f"1. Владелец бота ещё не добавил ключ в Railway Variables\n"
            f"2. Добавь свой ключ: /setkey (BYOK)\n\n"
            f"Вы написали: {message.text}"
        )
        return
    
    # --- Отправляем в AI ---
    wait_msg = await message.answer("⏳ Думаю...")
    
    # Простой системный промпт (позже заменим на динамическую сборку)
    system = "Ты — полезный ассистент. Отвечай кратко, по существу, на русском языке."
    
       answer, success = await ask_llm(
        prompt=message.text,
        user_id=message.from_user.id,
        model="xai/grok-beta",
        system_prompt=system
    )
    
    # Удаляем сообщение "Думаю..."
    try:
        await wait_msg.delete()
    except Exception:
        pass
    
    if success:
        source_icon = "🔑" if source == "byok" else "⚡"
        await message.answer(f"{source_icon} <b>Ответ AI:</b>\n\n{answer}")
    else:
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{answer}")

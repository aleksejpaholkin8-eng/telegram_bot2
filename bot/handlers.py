# ============================================
# ОБРАБОТЧИКИ (ЭТАП 5.1 — Исправлено шифрование)
# ============================================

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.states import UserRegistration, ByokInput
from db.database import async_session
from db.models import User, Role, Command as CommandModel, UserState, UserApiKey
from sqlalchemy import select

from services.llm_service import ask_llm, get_api_key
from services.tariff_service import check_token_limit
from services.role_router import select_roles
from services.prompt_builder import build_system_prompt
from services.encryption import encrypt_key  # ← ИСПРАВЛЕНИЕ: используем нормальное шифрование

router = Router()


# ============ ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ============

async def get_or_create_user(message: types.Message):
    """
    Находит пользователя в БД или создаёт нового.
    Тариф берётся из настроек (lite по умолчанию).
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
                tariff="lite"  # По умолчанию — Lite
            )
            session.add(user)
            await session.commit()
        
        # ❌ УБРАНО: принудительная смена тарифа на pro
        # Если нужно протестировать Pro — меняй тариф вручную через БД или /admin
        
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
        "• /setkey — ввести свой API-ключ (BYOK)\n\n"
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
    """Запускает диалог ввода BYOK-ключа"""
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
        # Фильтруем роли по тарифу пользователя
        if user.tariff == "lite":
            allowed = ["lite"]
        elif user.tariff == "pro":
            allowed = ["lite", "pro"]
        else:
            allowed = ["lite", "pro", "business"]
            
        result = await session.execute(
            select(Role).where(
                Role.is_active == True,
                Role.tier_access.in_(allowed)
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
        if user.tariff == "lite":
            allowed = ["lite"]
        elif user.tariff == "pro":
            allowed = ["lite", "pro"]
        else:
            allowed = ["lite", "pro", "business"]
            
        result = await session.execute(
            select(CommandModel).where(
                CommandModel.tier_access.in_(allowed)
            )
        )
        commands = result.scalars().all()

        text = f"⌨️ <b>Команды (тариф: {user.tariff.upper()}):</b>\n\n"
        for cmd in commands:
            icon = "✅" if cmd.tier_access == "lite" else "🔒"
            text += f"{icon} <b>{cmd.name}</b> — {cmd.description}\n"
        await message.answer(text)


@router.message(Command(commands="settariff"))
async def cmd_settariff(message: types.Message):
    """
    Команда только для владельца бота.
    Меняет тариф текущего пользователя.
    Формат: /settariff pro
    """
    from config.settings import settings
    
    # Проверяем, что команду вызвал владелец
    if message.from_user.id != settings.owner_id:
        await message.answer("⛔ Эта команда только для владельца бота.")
        return
    
    # Парсим аргумент (lite / pro / business)
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "🎫 <b>Смена тарифа</b>\n\n"
            "Формат: <code>/settariff lite</code>\n"
            "Формат: <code>/settariff pro</code>\n"
            "Формат: <code>/settariff business</code>\n\n"
            f"Твой текущий ID: <code>{message.from_user.id}</code>"
        )
        return
    
    new_tariff = args[1].lower()
    if new_tariff not in ["lite", "pro", "business"]:
        await message.answer("❌ Неверный тариф. Доступны: lite, pro, business")
        return
    
    # Меняем тариф в БД
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await message.answer("❌ Пользователь не найден. Сначала напиши /start")
            return
        
        old_tariff = user.tariff
        user.tariff = new_tariff
        await session.commit()
    
    await message.answer(
        f"✅ <b>Тариф изменён!</b>\n\n"
        f"Было: {old_tariff.upper()}\n"
        f"Стало: {new_tariff.upper()}\n\n"
        f"Перезапусти бота: /start"
    )


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


# ============ FSM: ВВОД КЛЮЧА BYOK (ИСПРАВЛЕННОЕ ШИФРОВАНИЕ) ============

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

    # ← ИСПРАВЛЕНИЕ: используем Fernet-шифрование вместо base64
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
    Pro/Business → выбор ролей → сборка промпта → AI
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

    # --- Проверяем наличие ключа (для модели по умолчанию) ---
    # Определяем провайдера из дефолтной модели
    default_model = "groq/llama-3.3-70b-versatile"
    provider = default_model.split("/")[0]
    
    api_key, source = await get_api_key(message.from_user.id, provider=provider)
    if not api_key:
        await message.answer(
            f"🔑 <b>Нет API-ключа</b>\n\n"
            f"Варианты:\n"
            f"1. Владелец бота ещё не добавил {provider.upper()}_API_KEY в Railway Variables\n"
            f"2. Добавь свой ключ: /setkey (BYOK)\n\n"
            f"Вы написали: {message.text}"
        )
        return

    # --- ВЫБИРАЕМ РОЛИ И СОБИРАЕМ ПРОМПТ ---
    wait_msg = await message.answer("⏳ Анализирую запрос и выбираю роли...")
    
    # 1. Роутер выбирает роли по keywords
    # Определяем max_roles из тарифа
    from services.tariff_service import check_feature_access
    _, max_roles = await check_feature_access(user.tariff, "max_roles")
    if max_roles == 0:
        max_roles = 5  # fallback
        
    selected_roles = await select_roles(message.from_user.id, message.text, max_roles=max_roles)
    
    # 2. Строим динамический системный промпт
    system_prompt = await build_system_prompt(message.from_user.id, selected_roles)
    
    # Показываем, какие роли активированы
    roles_names = ", ".join([r.name.split(":")[0] for r in selected_roles[:3]])
    try:
        await wait_msg.edit_text(f"⚡ Активированы роли: {roles_names}\n⏳ Думаю...")
    except Exception:
        pass

    # 3. Отправляем в AI с динамическим промптом
    answer, success = await ask_llm(
        prompt=message.text,
        user_id=message.from_user.id,
        model=default_model,
        system_prompt=system_prompt
    )

    # 4. Показываем ответ
    if success:
        source_icon = "🔑" if source == "byok" else "⚡"
        roles_info = f"\n\n<i>🎭 Активные роли: {roles_names}</i>" if selected_roles else ""
        await message.answer(f"{source_icon} <b>Ответ AI:</b>\n\n{answer}{roles_info}")
    else:
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{answer}")

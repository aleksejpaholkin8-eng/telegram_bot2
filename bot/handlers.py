# ============================================
# ОБРАБОТЧИКИ (ЭТАП 3 — LLM ИНТЕГРАЦИЯ)
# ============================================

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.states import UserRegistration, ByokSetup
from db.database import async_session
from db.models import User, Role, Command as CommandModel, TariffFeature, UserApiKey, UserState
from sqlalchemy import select
from services.llm_service import ask_llm, check_llm_access
from services.encryption import encrypt_key

router = Router()


# ============ ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ============

async def get_or_create_user(message: types.Message):
    """Находит пользователя в БД или создаёт нового"""
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
    """Приветствие + статус AI"""
    user = await get_or_create_user(message)
    has_llm, limit = await check_llm_access(message.from_user.id)
    llm_status = "✅ Доступен" if has_llm else "🚫 Недоступен (только Lite)"
    
    await message.answer(
        f"👋 <b>Привет, {user.first_name or 'друг'}!</b>\n\n"
        f"🎫 Тариф: <b>{user.tariff.upper()}</b>\n"
        f"🤖 AI: {llm_status}\n\n"
        f"📋 Команды:\n"
        f"/start — начало\n"
        f"/help — справка\n"
        f"/register — регистрация\n"
        f"/roles — роли\n"
        f"/commands — команды\n"
        f"/ask — задать вопрос AI\n"
        f"/mytariff — мой тариф и лимиты\n"
        f"/setkey — добавить свой API-ключ\n\n"
        f"Просто напиши что-нибудь — я повторю."
    )


@router.message(Command(commands="help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 <b>Справка (Этап 3)</b>\n\n"
        "• /start — перезапустить\n"
        "• /help — это сообщение\n"
        "• /register — сохранить имя и цель в базу\n"
        "• /roles — показать роли\n"
        "• /commands — показать команды\n"
        "• /ask [вопрос] — спросить AI (Pro/Business)\n"
        "• /mytariff — информация о тарифе\n"
        "• /setkey — добавить свой API-ключ (BYOK)\n\n"
        "💡 Бот подключён к Groq AI (Llama 3.1)!"
    )


@router.message(Command(commands="mytariff"))
async def cmd_mytariff(message: types.Message):
    """Показывает тариф и все функции"""
    user = await get_or_create_user(message)
    has_llm, limit = await check_llm_access(message.from_user.id)
    
    async with async_session() as session:
        result = await session.execute(
            select(TariffFeature).where(TariffFeature.tariff == user.tariff)
        )
        features = result.scalars().all()
    
    text = f"🎫 <b>Твой тариф: {user.tariff.upper()}</b>\n\n"
    text += f"🤖 Доступ к AI: {'✅ Да' if has_llm else '❌ Нет'}\n"
    text += f"📊 Лимит токенов/день: {limit if limit < 999999 else '♾️ Безлимит'}\n\n"
    text += "<b>Функции:</b>\n"
    for f in features:
        icon = "✅" if f.access else "❌"
        limit_str = f" (лимит: {f.limit_value})" if f.limit_value and f.limit_value < 999999 else ""
        text += f"{icon} {f.feature}{limit_str}\n"
    
    await message.answer(text)


@router.message(Command(commands="ask"))
async def cmd_ask(message: types.Message):
    """Диалог с AI: /ask вопрос"""
    # Вырезаем "/ask" из сообщения
    args = message.text.replace("/ask", "").strip()
    
    if not args:
        await message.answer(
            "🤖 <b>Задай вопрос AI</b>\n\n"
            "Напиши: <code>/ask твой вопрос</code>\n\n"
            "Пример:\n"
            "<code>/ask Объясни, что такое Python простыми словами</code>"
        )
        return
    
    # Показываем "печатает..." (анимация)
    await message.bot.send_chat_action(message.chat.id, "typing")
    
    # Отправляем вопрос в AI
    answer = await ask_llm(message.from_user.id, args)
    await message.answer(answer)


@router.message(Command(commands="setkey"))
async def cmd_setkey(message: types.Message, state: FSMContext):
    """Запускает диалог добавления BYOK-ключа"""
    user = await get_or_create_user(message)
    
    # Проверяем, доступен ли BYOK в тарифе
    async with async_session() as session:
        result = await session.execute(
            select(TariffFeature).where(
                TariffFeature.tariff == user.tariff,
                TariffFeature.feature == "byok"
            )
        )
        byok_feature = result.scalar_one_or_none()
    
    if not byok_feature or not byok_feature.access:
        await message.answer(
            "🚫 <b>BYOK недоступен</b>\n\n"
            "В тарифе <b>Lite</b> нельзя использовать свой API-ключ.\n"
            "Обновите тариф до <b>Pro</b> или <b>Business</b>."
        )
        return
    
    await state.set_state(ByokSetup.waiting_for_provider)
    await message.answer(
        "🔑 <b>Добавление своего API-ключа (BYOK)</b>\n\n"
        "Шаг 1 из 2\n"
        "Выбери провайдера:\n"
        "<code>groq</code>, <code>deepseek</code>, <code>openai</code>, <code>gemini</code>, <code>anthropic</code>\n\n"
        "Напиши название одним словом."
    )


@router.message(ByokSetup.waiting_for_provider)
async def process_provider(message: types.Message, state: FSMContext):
    """Шаг 1 BYOK: получаем провайдера"""
    provider = message.text.lower().strip()
    valid = ["groq", "deepseek", "openai", "gemini", "anthropic"]
    
    if provider not in valid:
        await message.answer(
            f"❌ Неизвестный провайдер.\n\n"
            f"Выбери из списка: {', '.join(valid)}"
        )
        return
    
    await state.update_data(provider=provider)
    await state.set_state(ByokSetup.waiting_for_key)
    await message.answer(
        f"Шаг 2 из 2\n"
        f"Введи свой API-ключ для <b>{provider}</b>:\n\n"
        f"⚠️ Ключ будет зашифрован и храниться безопасно."
    )


@router.message(ByokSetup.waiting_for_key)
async def process_key(message: types.Message, state: FSMContext):
    """Шаг 2 BYOK: получаем ключ, шифруем и сохраняем"""
    data = await state.get_data()
    provider = data["provider"]
    key = message.text.strip()
    
    try:
        encrypted = encrypt_key(key)
    except ValueError as e:
        await message.answer(f"❌ Ошибка шифрования: {e}")
        await state.clear()
        return
    
    async with async_session() as session:
        # Удаляем старый ключ этого провайдера, если есть
        result = await session.execute(
            select(UserApiKey).where(
                UserApiKey.user_id == message.from_user.id,
                UserApiKey.provider == provider
            )
        )
        old_key = result.scalar_one_or_none()
        if old_key:
            await session.delete(old_key)
        
        new_key = UserApiKey(
            user_id=message.from_user.id,
            provider=provider,
            key_encrypted=encrypted
        )
        session.add(new_key)
        await session.commit()
    
    await state.clear()
    await message.answer(
        f"✅ <b>Ключ сохранён!</b>\n\n"
        f"Провайдер: <b>{provider}</b>\n"
        f"Теперь бот использует твой ключ.\n\n"
        f"Проверь: <code>/ask привет</code>"
    )


# ============ СТАРЫЕ КОМАНДЫ (регистрация, роли и т.д.) ============

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
        user_state = result.scalar_one_or_none()
        if not user_state:
            user_state = UserState(
                user_id=message.from_user.id,
                json_passport={"name": data['name'], "goal": data['goal']}
            )
            session.add(user_state)
        else:
            user_state.json_passport = {"name": data['name'], "goal": data['goal']}
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
    
    text = f"🎭 <b>Доступные роли (тариф: {user.tariff.upper()}):</b>\n\n"
    for role in roles:
        tier_icon = "🆓" if role.tier_access == "lite" else "💎"
        text += f"{tier_icon} <b>{role.name}</b>\n"
        text += f"   🔑 {role.keywords}\n\n"
    text += f"📊 Всего: {len(roles)}"
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


@router.message()
async def echo_handler(message: types.Message):
    user = await get_or_create_user(message)
    await message.answer(
        f"🤖 <b>Эхо</b>\n\n"
        f"Вы написали: {message.text}\n"
        f"🎫 Тариф: {user.tariff.upper()}\n\n"
        f"Попробуй: /start, /help, /ask, /register, /roles, /commands"
    )

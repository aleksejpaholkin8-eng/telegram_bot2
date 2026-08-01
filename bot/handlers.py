# ============================================
# ОБРАБОТЧИКИ (ЭТАП 2 — РАБОТА С БАЗОЙ ДАННЫХ)
# ============================================

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.states import UserRegistration
from db.database import async_session
from db.models import User, Role, Command, TariffFeature
from sqlalchemy import select, func

router = Router()


# ============ ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ============

async def get_or_create_user(message: types.Message):
    """
    Находит пользователя в БД или создаёт нового.
    Вызывается при каждом сообщении.
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


# ============ КОМАНДЫ ============

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user = await get_or_create_user(message)
    await message.answer(
        f"👋 <b>Привет, {user.first_name or 'друг'}!</b>\n\n"
        f"🎫 Твой тариф: <b>{user.tariff.upper()}</b>\n\n"
        f"📋 Команды:\n"
        f"/start — начало\n"
        f"/help — справка\n"
        f"/register — регистрация в системе\n"
        f"/roles — список доступных ролей\n"
        f"/commands — доступные команды (!ТРЕКИ и др.)\n\n"
        f"Просто напиши что-нибудь — я повторю."
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 <b>Справка</b>\n\n"
        "• /start — перезапустить\n"
        "• /help — это сообщение\n"
        "• /register — сохранить имя и цель в базу\n"
        "• /roles — показать роли твоего тарифа\n"
        "• /commands — показать команды твоего тарифа\n\n"
        "💡 На Этапе 2 бот уже умеет работать с базой данных!"
    )


@router.message(Command("register"))
async def cmd_register(message: types.Message, state: FSMContext):
    await state.set_state(UserRegistration.waiting_for_name)
    await message.answer(
        "📝 <b>Регистрация в системе</b>\n\n"
        "Шаг 1 из 3\n"
        "Как тебя зовут?"
    )


# ============ FSM-ДИАЛОГ ============

@router.message(UserRegistration.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(UserRegistration.waiting_for_goal)
    await message.answer(
        f"Приятно познакомиться, <b>{message.text}</b>!\n\n"
        f"Шаг 2 из 3\n"
        f"Какая твоя главная цель?"
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
    
    # 💾 СОХРАНЯЕМ В БАЗУ ДАННЫХ!
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if user:
            from db.models import UserState
            # Создаём или обновляем состояние пользователя
            result2 = await session.execute(
                select(UserState).where(UserState.user_id == message.from_user.id)
            )
            user_state = result2.scalar_one_or_none()
            
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
        f"💾 Данные сохранены в базу данных PostgreSQL.\n"
        f"Даже если бот перезапустится — я тебя помню!"
    )


@router.message(UserRegistration.waiting_for_confirm, F.text.lower() == "нет")
async def process_confirm_no(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Регистрация отменена. Напиши /register, чтобы начать заново.")


@router.message(UserRegistration.waiting_for_confirm)
async def process_confirm_invalid(message: types.Message):
    await message.answer("Не понял. Напиши <b>да</b> или <b>нет</b>.")


# ============ НОВЫЕ КОМАНДЫ (БАЗА ДАННЫХ) ============

@router.message(Command("roles"))
async def cmd_roles(message: types.Message):
    """Показывает роли, доступные в тарифе пользователя"""
    user = await get_or_create_user(message)
    
    async with async_session() as session:
        # Фильтруем роли по тарифу
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
            text += f"   🔑 Ключевые слова: {role.keywords}\n\n"
        
        text += f"📊 Всего ролей: {len(roles)}"
        await message.answer(text)


@router.message(Command("commands"))
async def cmd_commands(message: types.Message):
    """Показывает команды, доступные в тарифе пользователя"""
    user = await get_or_create_user(message)
    
    async with async_session() as session:
        result = await session.execute(
            select(Command).where(
                Command.tier_access.in_(["lite", user.tariff])
            )
        )
        commands = result.scalars().all()
        
        text = f"⌨️ <b>Доступные команды (тариф: {user.tariff.upper()}):</b>\n\n"
        for cmd in commands:
            icon = "✅" if cmd.tier_access == "lite" else "🔒"
            text += f"{icon} <b>{cmd.name}</b> — {cmd.description}\n"
        
        await message.answer(text)


# ============ ЭХО ============

@router.message()
async def echo_handler(message: types.Message):
    user = await get_or_create_user(message)
    await message.answer(
        f"🤖 <b>Эхо</b>\n\n"
        f"Вы написали: {message.text}\n"
        f"🎫 Тариф: {user.tariff.upper()}\n\n"
        f"Попробуй: /start, /help, /register, /roles, /commands"
    )

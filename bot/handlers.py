# ============================================
# ОБРАБОТЧИКИ СООБЩЕНИЙ
# ============================================
# Здесь вся логика: команды, диалоги, ответы.

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.states import UserRegistration

# Создаём роутер — это "контейнер" для обработчиков
router = Router()


# ============ ОБЫЧНЫЕ КОМАНДЫ ============

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """
    Команда /start — первое приветствие.
    Показываем, что бот умеет.
    """
    await message.answer(
        "👋 <b>Привет!</b>\n\n"
        "Я — мультиагентный бот. Сейчас я на Этапе 1 обучения.\n\n"
        "📋 Команды:\n"
        "/start — начало работы\n"
        "/help — справка\n"
        "/register — демо-диалог (3 шага)\n\n"
        "Просто напиши что-нибудь — я повторю."
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Команда /help — список доступного"""
    await message.answer(
        "📖 <b>Справка</b>\n\n"
        "• /start — перезапустить бота\n"
        "• /help — показать это сообщение\n"
        "• /register — пройти демо-регистрацию\n\n"
        "В любой момент напиши /start, чтобы сбросить диалог."
    )


@router.message(Command("register"))
async def cmd_register(message: types.Message, state: FSMContext):
    """
    Команда /register — запускает FSM-диалог.
    Бот переходит в состояние "жду имя".
    """
    await state.set_state(UserRegistration.waiting_for_name)
    await message.answer(
        "📝 <b>Регистрация (демо)</b>\n\n"
        "Шаг 1 из 3\n"
        "Как тебя зовут?"
    )


# ============ ШАГИ ДИАЛОГА FSM ============

@router.message(UserRegistration.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    """
    Шаг 1: получили имя.
    Сохраняем в память и переходим к шагу 2.
    """
    await state.update_data(name=message.text)
    await state.set_state(UserRegistration.waiting_for_goal)
    await message.answer(
        f"Приятно познакомиться, <b>{message.text}</b>!\n\n"
        f"Шаг 2 из 3\n"
        f"Какая твоя главная цель? (например: изучить Python, найти работу...)"
    )


@router.message(UserRegistration.waiting_for_goal)
async def process_goal(message: types.Message, state: FSMContext):
    """
    Шаг 2: получили цель.
    Показываем сводку и просим подтвердить.
    """
    await state.update_data(goal=message.text)
    data = await state.get_data()
    
    await state.set_state(UserRegistration.waiting_for_confirm)
    await message.answer(
        f"📋 <b>Проверь данные:</b>\n\n"
        f"👤 Имя: {data['name']}\n"
        f"🎯 Цель: {data['goal']}\n\n"
        f"Шаг 3 из 3\n"
        f"Всё верно? Напиши <b>да</b> или <b>нет</b>."
    )


@router.message(UserRegistration.waiting_for_confirm, F.text.lower() == "да")
async def process_confirm_yes(message: types.Message, state: FSMContext):
    """
    Шаг 3: пользователь подтвердил.
    Очищаем состояние и прощаемся.
    """
    data = await state.get_data()
    await state.clear()
    await message.answer(
        f"✅ <b>Регистрация завершена!</b>\n\n"
        f"👤 Имя: {data['name']}\n"
        f"🎯 Цель: {data['goal']}\n\n"
        f"💡 Пока данные хранятся только в памяти.\n"
        f"На Этапе 2 мы научим бота сохранять их в базу данных."
    )


@router.message(UserRegistration.waiting_for_confirm, F.text.lower() == "нет")
async def process_confirm_no(message: types.Message, state: FSMContext):
    """Пользователь отказался — сбрасываем диалог."""
    await state.clear()
    await message.answer(
        "❌ Регистрация отменена.\n\n"
        "Напиши /register, чтобы начать заново."
    )


@router.message(UserRegistration.waiting_for_confirm)
async def process_confirm_invalid(message: types.Message):
    """
    Если на шаге 3 написали что-то кроме "да" или "нет".
    """
    await message.answer(
        "Не понял. Пожалуйста, напиши <b>да</b> или <b>нет</b>."
    )


# ============ ЭХО (по умолчанию) ============

@router.message()
async def echo_handler(message: types.Message):
    """
    Если сообщение не попало ни в одну команду и не в FSM —
    отвечаем эхом.
    """
    await message.answer(
        f"🤖 <b>Эхо-режим</b>\n\n"
        f"Вы написали: {message.text}\n\n"
        f"Попробуй команды:\n"
        f"/start, /help, /register"
    )

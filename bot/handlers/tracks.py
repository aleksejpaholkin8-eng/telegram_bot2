from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from bot.states import TrackMenu, FocusInput
from db.database import async_session
from db.models import UserState
from bot.handlers.admin import _send_admin_menu

router = Router()


# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ТРЕКОВ ============

def _get_tracks(user_state: UserState) -> list:
    """Превращает tracks в нормализованный список словарей"""
    tracks = user_state.tracks or []
    normalized = []
    for t in tracks:
        if isinstance(t, str):
            normalized.append({"name": t, "status": "active"})
        elif isinstance(t, dict):
            normalized.append(t)
    return normalized


def _save_tracks(user_state: UserState, tracks: list):
    """Сохраняет треки обратно в объект состояния (force dirty для JSON)"""
    import copy
    user_state.tracks = copy.deepcopy(tracks)
    flag_modified(user_state, "tracks")


# ============ /SYSTEM — ГЛАВНОЕ МЕНЮ ============

@router.message(Command(commands=["system", "menu"]))
async def cmd_system(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="🎯 Треки", callback_data="sys:tracks:menu")
    builder.button(text="⚡ Фокус", callback_data="sys:focus:menu")
    builder.button(text="📊 Прогресс", callback_data="sys:progress")
    builder.button(text="🧠 AI-режим", callback_data="sys:ai_mode")
    builder.button(text="📋 Мои данные", callback_data="sys:profile")
    builder.adjust(2, 2, 1)

    await message.answer(
        "🎛 <b>Главное меню Nexus AI</b>\n\n"
        "Выбери раздел кнопкой ниже.\n\n"
        "💡 Или используй текстовые команды:\n"
        "<code>!ТРЕКИ</code>, <code>!ФОКУС</code> и т.д.",
        reply_markup=builder.as_markup()
    )


# ============ ТРЕКИ (ИНТЕРАКТИВНОЕ МЕНЮ) ============

@router.callback_query(F.data == "sys:tracks:menu")
async def sys_tracks_menu(callback: types.CallbackQuery):
    """
    Показывает список треков с кнопками.
    Кнопки строятся от списка: active + paused (важно для индексов!)
    """
    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == callback.from_user.id)
        )
        user_state = result.scalar_one_or_none()

    tracks = _get_tracks(user_state) if user_state else []
    active = [t for t in tracks if t.get("status") == "active"]
    paused = [t for t in tracks if t.get("status") == "paused"]

    text = (
        "🎯 <b>Управление треками</b>\n\n"
        f"🟢 Активных: {len(active)} | ⏸ На паузе: {len(paused)}\n\n"
    )

    keyboard = []
    all_tracks = active + paused  # ← Этот порядок используем и в меню, и в обработчике!

    if not all_tracks:
        text += "У тебя пока нет треков.\n\n<b>💡 Быстрое добавление:</b>"
        templates = [
            ("🇰🇷 Корея/TOPIK", "Корея/TOPIK"),
            ("🏗 Строительство/МОК", "Строительство/МОК"),
            ("💼 Карьера/Вахта", "Карьера/Вахта"),
            ("📈 Инвестиции", "Инвестиции"),
            ("🧠 ИИ/Обучение", "ИИ/Обучение"),
        ]
        for btn_text, track_name in templates:
            keyboard.append([InlineKeyboardButton(
                text=btn_text,
                callback_data=f"sys:track:add:{track_name}"
            )])
    else:
        for idx, t in enumerate(all_tracks):
            icon = "🟢" if t.get("status") == "active" else "⏸"
            text += f"{icon} <b>{t['name']}</b>\n"

            # Кнопки с подписями треков для ясности
            action_row = []
            short_name = t['name'][:15]

            if t.get("status") == "active":
                action_row.append(InlineKeyboardButton(
                    text=f"⏸ {short_name}",
                    callback_data=f"sys:track:pause:{idx}"
                ))
            else:
                action_row.append(InlineKeyboardButton(
                    text=f"▶️ {short_name}",
                    callback_data=f"sys:track:resume:{idx}"
                ))
            action_row.append(InlineKeyboardButton(
                text=f"❌ {short_name}",
                callback_data=f"sys:track:delete:{idx}"
            ))
            keyboard.append(action_row)

    keyboard.append([InlineKeyboardButton(text="➕ Добавить трек", callback_data="sys:tracks:add")])
    keyboard.append([InlineKeyboardButton(text="← Назад в меню", callback_data="sys:main")])

    try:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    except Exception as e:
        if "message is not modified" in str(e):
            pass
        else:
            raise
    await callback.answer()


@router.callback_query(F.data.startswith("sys:track:"))
async def sys_track_action(callback: types.CallbackQuery):
    """
    Обрабатывает нажатие ❌, ⏸, ▶️ у конкретного трека.
    Формат: sys:track:delete:0, sys:track:pause:1 и т.д.
    
    ← ИСПРАВЛЕНИЕ: восстанавливаем тот же порядок active+paused, 
    что при создании кнопок. Иначе индекс указывает не на тот трек!
    """
    parts = callback.data.split(":")
    action = parts[2]
    idx = int(parts[3])

    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == callback.from_user.id)
        )
        user_state = result.scalar_one_or_none()

        if not user_state:
            await callback.answer("❌ Ошибка: состояние не найдено", show_alert=True)
            return

        tracks = _get_tracks(user_state)

        # ← ИСПРАВЛЕНИЕ: восстанавливаем порядок КАК В МЕНЮ (active + paused)
        active = [t for t in tracks if t.get("status") == "active"]
        paused = [t for t in tracks if t.get("status") == "paused"]
        all_tracks = active + paused

        if idx >= len(all_tracks):
            await callback.answer("❌ Трек не найден (список изменился)", show_alert=True)
            return

        track = all_tracks[idx]  # ← Берём из all_tracks, а не из tracks!
        name = track["name"]

        if action == "delete":
            # Показываем подтверждение вместо мгновенного удаления
            keyboard = [
                [InlineKeyboardButton(
                    text=f"🗑 Да, удалить «{name}»",
                    callback_data=f"sys:confirm_delete:{idx}"
                )],
                [InlineKeyboardButton(
                    text="← Отмена",
                    callback_data="sys:tracks:menu"
                )]
            ]
            await callback.message.edit_text(
                f"⚠️ <b>Подтверди удаление</b>\n\n"
                f"Трек: «<b>{name}</b>»\n\n"
                f"Это действие необратимо.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
            )
            await callback.answer()
            return

        elif action == "pause":
            # Находим в оригинальном списке и меняем статус
            for t in tracks:
                if t["name"] == name:
                    t["status"] = "paused"
                    break
            msg = f"⏸ Трек «{name}» на паузе"

        elif action == "resume":
            for t in tracks:
                if t["name"] == name:
                    t["status"] = "active"
                    break
            msg = f"▶️ Трек «{name}» возобновлён"

        else:
            await callback.answer("❌ Неизвестное действие", show_alert=True)
            return

        _save_tracks(user_state, tracks)
        await session.commit()

    await callback.answer(msg)

    # Обновляем меню треков
    await sys_tracks_menu(callback)


@router.callback_query(F.data.startswith("sys:confirm_delete:"))
async def sys_track_confirm_delete(callback: types.CallbackQuery):
    """Подтверждённое удаление трека"""
    parts = callback.data.split(":")
    idx = int(parts[2])

    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == callback.from_user.id)
        )
        user_state = result.scalar_one_or_none()

        if not user_state:
            await callback.answer("❌ Ошибка: состояние не найдено", show_alert=True)
            return

        tracks = _get_tracks(user_state)

        # Восстанавливаем тот же порядок active + paused
        active = [t for t in tracks if t.get("status") == "active"]
        paused = [t for t in tracks if t.get("status") == "paused"]
        all_tracks = active + paused

        if idx >= len(all_tracks):
            await callback.answer("❌ Трек не найден", show_alert=True)
            return

        track = all_tracks[idx]
        name = track["name"]

        # Удаляем по имени (надёжнее чем по индексу)
        tracks = [t for t in tracks if t["name"] != name]
        _save_tracks(user_state, tracks)
        await session.commit()

    await callback.answer(f"🗑 Трек «{name}» удалён")
    await sys_tracks_menu(callback)


@router.callback_query(F.data.startswith("sys:template:add:"))
async def sys_track_add_template(callback: types.CallbackQuery):
    """Добавляет трек из шаблона"""
    name = callback.data.split(":", 3)[3]

    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == callback.from_user.id)
        )
        user_state = result.scalar_one_or_none()

        if not user_state:
            user_state = UserState(
                user_id=callback.from_user.id,
                tracks=[],
                json_passport={},
                counters={}
            )
            session.add(user_state)

        tracks = _get_tracks(user_state)

        if any(t["name"].lower() == name.lower() for t in tracks):
            await callback.answer(f"⚠️ Трек «{name}» уже есть", show_alert=True)
        else:
            tracks.append({"name": name, "status": "active", "hours": 0.0, "goal_hours": 0.0})
            _save_tracks(user_state, tracks)
            await session.commit()
            await callback.answer(f"✅ Трек «{name}» добавлен")

    await sys_tracks_menu(callback)
    

@router.callback_query(F.data == "sys:tracks:add")
async def sys_tracks_add_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(TrackMenu.waiting_for_name)
    await state.update_data(action="add")

    await callback.message.answer(
        "➕ <b>Добавление трека</b>\n\n"
        "Введи название нового трека.\n"
        "Можно любое название — без ограничений!\n"
        "Примеры:\n"
        "• <code>Корея/TOPIK</code>\n"
        "• <code>Строительство/МОК</code>\n"
        "• <code>Мой личный трек</code>\n\n"
        "Для отмены напиши /start"
    )
    await callback.answer()


@router.message(TrackMenu.waiting_for_name)
async def sys_tracks_process_name(message: types.Message, state: FSMContext):
    text = message.text.strip()

    # === ЗАЩИТА: отмена по /start ===
    if text == "/start":
        await state.clear()
        await cmd_system(message)
        return

    # === ЗАЩИТА: reply-кнопки меню — не название трека ===
    if text in ("🎛 Меню", "🔧 Админ-меню"):
        await state.clear()
        if text == "🎛 Меню":
            await cmd_system(message)
        else:
            await _send_admin_menu(message, message.from_user.id)
        return

    # === ЗАЩИТА: команды и !-команды — отмена диалога ===
    if text.startswith("/") or text.startswith("!"):
        await state.clear()
        await message.answer("❌ Добавление трека отменено.")
        return

    data = await state.get_data()
    action = data.get("action")
    name = text

    if action != "add":
        await state.clear()
        return

    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == message.from_user.id)
        )
        user_state = result.scalar_one_or_none()

        if not user_state:
            user_state = UserState(
                user_id=message.from_user.id,
                tracks=[],
                json_passport={},
                counters={}
            )
            session.add(user_state)

        tracks = _get_tracks(user_state)

        if any(t["name"].lower() == name.lower() for t in tracks):
            await message.answer(f"⚠️ Трек «{name}» уже есть.")
            await state.clear()
            return

        tracks.append({"name": name, "status": "active", "hours": 0.0, "goal_hours": 0.0})
        _save_tracks(user_state, tracks)
        await session.commit()

        await message.answer(
            f"✅ Трек «<b>{name}</b>» добавлен!\n\n"
            f"Всего треков: {len(tracks)}"
        )

    await state.clear()

    builder = InlineKeyboardBuilder()
    builder.button(text="🎯 К трекам", callback_data="sys:tracks:menu")
    builder.button(text="🎛 Главное меню", callback_data="sys:main")
    builder.adjust(2)

    await message.answer("Что дальше?", reply_markup=builder.as_markup())


# ============ ЗАГЛУШКИ → РАБОЧИЕ ВЕРСИИ ============

@router.callback_query(F.data == "sys:focus:menu")
async def sys_focus_menu(callback: types.CallbackQuery, state: FSMContext):
    """Интерактивная установка фокуса через FSM"""
    await state.set_state(FocusInput.waiting_for_topic)
    await callback.message.answer(
        "🎯 <b>Установка фокуса</b>\n\n"
        "Введи тему, на которой хочешь сфокусироваться.\n"
        "Примеры: <code>Корея</code>, <code>Строительство</code>, <code>Инвестиции</code>\n\n"
        "Для отмены напиши /start"
    )
    await callback.answer()



@router.message(FocusInput.waiting_for_topic)
async def sys_focus_process(message: types.Message, state: FSMContext):
    """Сохраняет фокус из FSM-диалога"""
    text = message.text.strip()

    # === ЗАЩИТА: отмена по /start ===
    if text == "/start":
        await state.clear()
        await cmd_system(message)
        return

    # === ЗАЩИТА: reply-кнопки меню — не тема фокуса ===
    if text in ("🎛 Меню", "🔧 Админ-меню"):
        await state.clear()
        if text == "🎛 Меню":
            await cmd_system(message)
        else:
            await _send_admin_menu(message, message.from_user.id)
        return

    # === ЗАЩИТА: команды и !-команды — отмена диалога ===
    if text.startswith("/") or text.startswith("!"):
        await state.clear()
        await message.answer("❌ Установка фокуса отменена.")
        return

    topic = text
    if not topic:
        await message.answer("❌ Тема не может быть пустой. Попробуй ещё раз.")
        return

    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == message.from_user.id)
        )
        us = result.scalar_one_or_none()
        if not us:
            us = UserState(
                user_id=message.from_user.id,
                json_passport={"focus": topic},
                tracks=[],
                counters={}
            )
            session.add(us)
        else:
            passport = us.json_passport or {}
            passport["focus"] = topic
            us.json_passport = passport
        await session.commit()

    await state.clear()
    await message.answer(
        f"🎯 <b>Фокус установлен:</b> <i>{topic}</i>\n\n"
        f"AI будет приоритизировать эту тему в ответах.\n"
        f"Сбросить: <code>!СБРОС</code>"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="🎛 Главное меню", callback_data="sys:main")
    await message.answer("Что дальше?", reply_markup=builder.as_markup())


@router.callback_query(F.data == "sys:progress")
async def sys_progress_callback(callback: types.CallbackQuery):
    """Прогресс через кнопку /system"""
    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == callback.from_user.id)
        )
        user_state = result.scalar_one_or_none()
        tracks = _get_tracks(user_state) if user_state else []

    active = [t for t in tracks if t.get("status") == "active"]
    paused = [t for t in tracks if t.get("status") == "paused"]

    if not tracks:
        text = (
            "📊 <b>Прогресс</b>\n\n"
            "У тебя пока нет треков.\n"
            "Добавь первый через <code>/system</code> → 🎯 Треки"
        )
    else:
        text = "📊 <b>Прогресс по трекам</b>\n\n"
        for t in active:
            hrs = t.get("hours", 0)
            text += f"🟢 <b>{t['name']}</b> — {hrs}ч\n"
        for t in paused:
            hrs = t.get("hours", 0)
            text += f"⏸ <b>{t['name']}</b> — {hrs}ч\n"
        text += f"\n📈 Всего: {len(tracks)} | Активных: {len(active)} | На паузе: {len(paused)}"

    builder = InlineKeyboardBuilder()
    builder.button(text="← Назад в меню", callback_data="sys:main")

    await callback.message.answer(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "sys:ai_mode")
async def sys_ai_mode(callback: types.CallbackQuery):
    """Переключение режима ответа AI"""
    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == callback.from_user.id)
        )
        us = result.scalar_one_or_none()
        mode = "long"
        if us and us.json_passport:
            mode = us.json_passport.get("response_mode", "long")

    current = "📖 Развёрнутый" if mode == "long" else "📄 Сжатый"

    text = (
        f"🧠 <b>AI-режим ответа</b>\n\n"
        f"Текущий: <b>{current}</b>\n\n"
        f"Выбери формат:"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="📄 Сжатый (!ЖМИ)", callback_data="sys:ai_mode:set:short")
    builder.button(text="📖 Развёрнутый (!РАЗВЕРНИ)", callback_data="sys:ai_mode:set:long")
    builder.button(text="🔄 Сброс (!СБРОС)", callback_data="sys:ai_mode:set:reset")
    builder.button(text="← Назад", callback_data="sys:main")
    builder.adjust(1)

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("sys:ai_mode:set:"))
async def sys_ai_mode_set(callback: types.CallbackQuery):
    """Применяет выбранный AI-режим"""
    mode = callback.data.split(":")[3]

    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == callback.from_user.id)
        )
        us = result.scalar_one_or_none()
        if not us:
            us = UserState(
                user_id=callback.from_user.id,
                json_passport={},
                tracks=[],
                counters={}
            )
            session.add(us)

        passport = us.json_passport or {}
        if mode == "reset":
            passport.pop("response_mode", None)
            passport.pop("focus", None)
            msg = "🔄 Настройки сброшены"
        else:
            passport["response_mode"] = mode
            msg = "📄 Сжатый режим" if mode == "short" else "📖 Развёрнутый режим"
        us.json_passport = passport
        await session.commit()

    await callback.answer(msg)
    # Возвращаемся в главное меню
    await cmd_system(callback.message)


@router.callback_query(F.data == "sys:profile")
async def sys_profile(callback: types.CallbackQuery):
    """Показывает JSON-паспорт пользователя"""
    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == callback.from_user.id)
        )
        us = result.scalar_one_or_none()

        from db.models import User
        result2 = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result2.scalar_one_or_none()

    passport = us.json_passport if us else {}
    tracks = _get_tracks(us) if us else []
    active = [t for t in tracks if t.get("status") == "active"]
    paused = [t for t in tracks if t.get("status") == "paused"]

    name = passport.get("name", callback.from_user.first_name or "Не указано")
    goal = passport.get("goal", "Не указана")
    focus = passport.get("focus", "Не установлен")
    mode = "📖 Развёрнутый" if passport.get("response_mode") != "short" else "📄 Сжатый"
    tariff = user.tariff if user else "lite"

    text = (
        f"📋 <b>Мои данные</b>\n\n"
        f"👤 <b>Имя:</b> {name}\n"
        f"🎯 <b>Цель:</b> {goal}\n"
        f"⚡ <b>Фокус:</b> {focus}\n"
        f"🧠 <b>Режим AI:</b> {mode}\n"
        f"💎 <b>Тариф:</b> {tariff.upper()}\n\n"
        f"📊 <b>Треки:</b> {len(tracks)} (🟢{len(active)} / ⏸{len(paused)})"
    )

    if tracks:
        text += "\n\n<b>Активные:</b>\n"
        for t in active:
            text += f"• {t['name']}\n"
        if paused:
            text += "\n<b>На паузе:</b>\n"
            for t in paused:
                text += f"• {t['name']}\n"

    builder = InlineKeyboardBuilder()
    builder.button(text="← Назад", callback_data="sys:main")

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "sys:main")
async def sys_back_to_main(callback: types.CallbackQuery):
    await cmd_system(callback.message)
    await callback.answer()


# ============ ЗАГЛУШКИ ДЛЯ ОСТАЛЬНЫХ РАЗДЕЛОВ /system ============


@router.callback_query(F.data == "sys:main")
async def sys_back_to_main(callback: types.CallbackQuery):
    await cmd_system(callback.message)
    await callback.answer()


# ============ REPLY-КНОПКИ ============

@router.message(F.text == "🎛 Меню")
async def user_menu_button(message: types.Message):
    await cmd_system(message)


@router.message(F.text == "🔧 Админ-меню")
async def admin_menu_button(message: types.Message):
    await _send_admin_menu(message, message.from_user.id)

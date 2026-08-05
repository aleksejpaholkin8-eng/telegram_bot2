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


def _get_tracks(user_state: UserState) -> list:
    tracks = user_state.tracks or []
    return [{"name": t, "status": "active"} if isinstance(t, str) else t for t in tracks]


def _save_tracks(user_state: UserState, tracks: list):
    import copy
    user_state.tracks = copy.deepcopy(tracks)
    flag_modified(user_state, "tracks")


def _guard_cancel(text: str, state: FSMContext, message: types.Message):
    if text == "/start":
        return True
    if text in ("🎛 Меню", "🔧 Админ-меню"):
        return True
    if text.startswith("/") or text.startswith("!"):
        return True
    return False


async def _guard_handle(text: str, state: FSMContext, message: types.Message):
    await state.clear()
    if text == "/start" or text == "🎛 Меню":
        await cmd_system(message)
    elif text == "🔧 Админ-меню":
        await _send_admin_menu(message, message.from_user.id)
    else:
        await message.answer("❌ Действие отменено.")


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


@router.callback_query(F.data == "sys:tracks:menu")
async def sys_tracks_menu(callback: types.CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == callback.from_user.id)
        )
        user_state = result.scalar_one_or_none()

    tracks = _get_tracks(user_state) if user_state else []
    active = [t for t in tracks if t.get("status") == "active"]
    paused = [t for t in tracks if t.get("status") == "paused"]
    all_tracks = active + paused

    text = f"🎯 <b>Управление треками</b>\n\n🟢 Активных: {len(active)} | ⏸ На паузе: {len(paused)}\n\n"
    keyboard = []

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
            keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"sys:template:add:{track_name}")])
    else:
        for idx, t in enumerate(all_tracks):
            icon = "🟢" if t.get("status") == "active" else "⏸"
            text += f"{icon} <b>{t['name']}</b>\n"
            short_name = t['name'][:15]
            action = "pause" if t.get("status") == "active" else "resume"
            action_icon = "⏸" if action == "pause" else "▶️"
            keyboard.append([
                InlineKeyboardButton(text=f"{action_icon} {short_name}", callback_data=f"sys:track:{action}:{idx}"),
                InlineKeyboardButton(text=f"❌ {short_name}", callback_data=f"sys:track:delete:{idx}"),
            ])

    keyboard.append([InlineKeyboardButton(text="➕ Добавить трек", callback_data="sys:tracks:add")])
    keyboard.append([InlineKeyboardButton(text="← Назад в меню", callback_data="sys:main")])

    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()


@router.callback_query(F.data.startswith("sys:track:"))
async def sys_track_action(callback: types.CallbackQuery):
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
        active = [t for t in tracks if t.get("status") == "active"]
        paused = [t for t in tracks if t.get("status") == "paused"]
        all_tracks = active + paused

        if idx >= len(all_tracks):
            await callback.answer("❌ Трек не найден", show_alert=True)
            return

        track = all_tracks[idx]
        name = track["name"]

        if action == "delete":
            keyboard = [
                [InlineKeyboardButton(text=f"🗑 Да, удалить «{name}»", callback_data=f"sys:confirm_delete:{idx}")],
                [InlineKeyboardButton(text="← Отмена", callback_data="sys:tracks:menu")],
            ]
            await callback.message.edit_text(
                f"⚠️ <b>Подтверди удаление</b>\n\nТрек: «<b>{name}</b>»\n\nЭто действие необратимо.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
            )
            await callback.answer()
            return

        if action == "pause":
            msg = f"⏸ Трек «{name}» на паузе"
            for t in tracks:
                if t["name"] == name:
                    t["status"] = "paused"
                    break
        elif action == "resume":
            msg = f"▶️ Трек «{name}» возобновлён"
            for t in tracks:
                if t["name"] == name:
                    t["status"] = "active"
                    break
        else:
            await callback.answer("❌ Неизвестное действие", show_alert=True)
            return

        _save_tracks(user_state, tracks)
        await session.commit()

    await callback.answer(msg)
    await sys_tracks_menu(callback)


@router.callback_query(F.data.startswith("sys:confirm_delete:"))
async def sys_track_confirm_delete(callback: types.CallbackQuery):
    idx = int(callback.data.split(":")[2])

    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == callback.from_user.id)
        )
        user_state = result.scalar_one_or_none()
        if not user_state:
            await callback.answer("❌ Ошибка", show_alert=True)
            return

        tracks = _get_tracks(user_state)
        active = [t for t in tracks if t.get("status") == "active"]
        paused = [t for t in tracks if t.get("status") == "paused"]
        all_tracks = active + paused

        if idx >= len(all_tracks):
            await callback.answer("❌ Трек не найден", show_alert=True)
            return

        name = all_tracks[idx]["name"]
        tracks = [t for t in tracks if t["name"] != name]
        _save_tracks(user_state, tracks)
        await session.commit()

    await callback.answer(f"🗑 Трек «{name}» удалён")
    await sys_tracks_menu(callback)


@router.callback_query(F.data.startswith("sys:template:add:"))
async def sys_track_add_template(callback: types.CallbackQuery):
    name = callback.data.split(":", 3)[3]

    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == callback.from_user.id)
        )
        user_state = result.scalar_one_or_none()
        if not user_state:
            user_state = UserState(user_id=callback.from_user.id, tracks=[], json_passport={}, counters={})
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
    if _guard_cancel(text, state, message):
        return await _guard_handle(text, state, message)

    data = await state.get_data()
    if data.get("action") != "add":
        await state.clear()
        return

    name = text
    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == message.from_user.id)
        )
        user_state = result.scalar_one_or_none()
        if not user_state:
            user_state = UserState(user_id=message.from_user.id, tracks=[], json_passport={}, counters={})
            session.add(user_state)

        tracks = _get_tracks(user_state)
        if any(t["name"].lower() == name.lower() for t in tracks):
            await message.answer(f"⚠️ Трек «{name}» уже есть.")
            await state.clear()
            return

        tracks.append({"name": name, "status": "active", "hours": 0.0, "goal_hours": 0.0})
        _save_tracks(user_state, tracks)
        await session.commit()
        await message.answer(f"✅ Трек «<b>{name}</b>» добавлен!\n\nВсего треков: {len(tracks)}")

    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text="🎯 К трекам", callback_data="sys:tracks:menu")
    builder.button(text="🎛 Главное меню", callback_data="sys:main")
    builder.adjust(2)
    await message.answer("Что дальше?", reply_markup=builder.as_markup())


@router.callback_query(F.data == "sys:focus:menu")
async def sys_focus_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(FocusInput.waiting_for_topic)
    await callback.message.answer(
        "🎯 <b>Установка фокуса</b>\n\n"
        "Введи тему:\n"
        "Примеры: <code>Корея</code>, <code>Строительство</code>, <code>Инвестиции</code>\n\n"
        "Для отмены напиши /start"
    )
    await callback.answer()


@router.message(FocusInput.waiting_for_topic)
async def sys_focus_process(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if _guard_cancel(text, state, message):
        return await _guard_handle(text, state, message)

    if not text:
        await message.answer("❌ Тема не может быть пустой.")
        return

    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == message.from_user.id)
        )
        us = result.scalar_one_or_none()
        if not us:
            us = UserState(user_id=message.from_user.id, json_passport={"focus": text}, tracks=[], counters={})
            session.add(us)
        else:
            passport = us.json_passport or {}
            passport["focus"] = text
            us.json_passport = passport
        await session.commit()

    await state.clear()
    await message.answer(
        f"🎯 <b>Фокус установлен:</b> <i>{text}</i>\n\n"
        "AI будет приоритизировать эту тему.\n"
        "Сбросить: <code>!СБРОС</code>"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="🎛 Главное меню", callback_data="sys:main")
    await message.answer("Что дальше?", reply_markup=builder.as_markup())


@router.callback_query(F.data == "sys:progress")
async def sys_progress_callback(callback: types.CallbackQuery):
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
            text += f"🟢 <b>{t['name']}</b> — {t.get('hours', 0)}ч\n"
        for t in paused:
            text += f"⏸ <b>{t['name']}</b> — {t.get('hours', 0)}ч\n"
        text += f"\n📈 Всего: {len(tracks)} | Активных: {len(active)} | На паузе: {len(paused)}"

    builder = InlineKeyboardBuilder()
    builder.button(text="← Назад в меню", callback_data="sys:main")
    await callback.message.answer(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "sys:ai_mode")
async def sys_ai_mode(callback: types.CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == callback.from_user.id)
        )
        us = result.scalar_one_or_none()
        mode = us.json_passport.get("response_mode", "long") if us and us.json_passport else "long"

    current = "📖 Развёрнутый" if mode == "long" else "📄 Сжатый"
    text = f"🧠 <b>AI-режим ответа</b>\n\nТекущий: <b>{current}</b>\n\nВыбери формат:"

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
    mode = callback.data.split(":")[3]

    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == callback.from_user.id)
        )
        us = result.scalar_one_or_none()
        if not us:
            us = UserState(user_id=callback.from_user.id, json_passport={}, tracks=[], counters={})
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
    await cmd_system(callback.message)


@router.callback_query(F.data == "sys:profile")
async def sys_profile(callback: types.CallbackQuery):
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
        text += "\n\n<b>Активные:</b>\n" + "\n".join(f"• {t['name']}" for t in active)
        if paused:
            text += "\n\n<b>На паузе:</b>\n" + "\n".join(f"• {t['name']}" for t in paused)

    builder = InlineKeyboardBuilder()
    builder.button(text="← Назад", callback_data="sys:main")
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "sys:main")
async def sys_back_to_main(callback: types.CallbackQuery):
    await cmd_system(callback.message)
    await callback.answer()


@router.message(F.text == "🎛 Меню")
async def user_menu_button(message: types.Message):
    await cmd_system(message)


@router.message(F.text == "🔧 Админ-меню")
async def admin_menu_button(message: types.Message):
    await _send_admin_menu(message, message.from_user.id)

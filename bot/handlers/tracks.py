# ============================================
# ТРЕКИ, МЕНЮ СИСТЕМЫ И ЗАГЛУШКИ РАЗДЕЛОВ
# ============================================

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from bot.states import TrackMenu
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
        text += "У тебя пока нет треков.\n"
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
            tracks = [t for t in tracks if t["name"] != name]
            msg = f"🗑 Трек «{name}» удалён"

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
    data = await state.get_data()
    action = data.get("action")
    name = message.text.strip()

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

        tracks.append({"name": name, "status": "active"})
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


# ============ ЗАГЛУШКИ ДЛЯ ОСТАЛЬНЫХ РАЗДЕЛОВ /system ============

@router.callback_query(F.data == "sys:focus:menu")
async def sys_focus_stub(callback: types.CallbackQuery):
    await callback.answer("⚡ Фокус — в разработке", show_alert=True)


@router.callback_query(F.data == "sys:progress")
async def sys_progress_stub(callback: types.CallbackQuery):
    await callback.answer("📊 Прогресс — в разработке", show_alert=True)


@router.callback_query(F.data == "sys:ai_mode")
async def sys_ai_mode_stub(callback: types.CallbackQuery):
    await callback.answer("🧠 AI-режим — в разработке", show_alert=True)


@router.callback_query(F.data == "sys:profile")
async def sys_profile_stub(callback: types.CallbackQuery):
    await callback.answer("📋 Мои данные — в разработке", show_alert=True)


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

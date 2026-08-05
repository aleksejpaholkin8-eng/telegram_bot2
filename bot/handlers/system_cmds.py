from aiogram import Router, types, F
from sqlalchemy import select

from db.database import async_session
from db.models import UserState
from bot.handlers.tracks import _get_tracks, _save_tracks

router = Router()


# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============

async def _set_response_mode(message: types.Message, mode: str):
    """Устанавливает режим ответа (short/long) в json_passport"""
    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == message.from_user.id)
        )
        us = result.scalar_one_or_none()
        if not us:
            us = UserState(
                user_id=message.from_user.id,
                json_passport={"response_mode": mode},
                tracks=[],
                counters={}
            )
            session.add(us)
        else:
            passport = us.json_passport or {}
            passport["response_mode"] = mode
            us.json_passport = passport
        await session.commit()

    mode_text = "📄 Сжатый (только тезисы)" if mode == "short" else "📖 Развёрнутый (полный ответ)"
    await message.answer(
        f"✅ Режим ответа: <b>{mode_text}</b>\n\n"
        f"Следующий запрос к AI будет в этом формате.\n"
        f"Сбросить: <code>!СБРОС</code>"
    )


async def _set_focus(message: types.Message, topic: str):
    """Устанавливает фокус-тему в json_passport"""
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

    await message.answer(
        f"🎯 <b>Фокус установлен:</b> <i>{topic}</i>\n\n"
        f"AI будет приоритизировать эту тему в следующих ответах.\n"
        f"Сбросить: <code>!СБРОС</code>"
    )


async def _reset_settings(message: types.Message):
    """Сбрасывает response_mode и focus"""
    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == message.from_user.id)
        )
        us = result.scalar_one_or_none()
        if us:
            passport = us.json_passport or {}
            passport.pop("response_mode", None)
            passport.pop("focus", None)
            us.json_passport = passport
            await session.commit()

    await message.answer("🔄 <b>Настройки сброшены.</b>\n\nСтандартный режим, фокус снят.")


# ============ ГЛАВНЫЙ ОБРАБОТЧИК !-КОМАНД ============

@router.message(F.text.startswith("!"))
async def system_commands(message: types.Message):
    text = message.text.strip()
    parts = text.split(maxsplit=2)
    cmd = parts[0].upper()

    # Получаем или создаём user_state (один раз)
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
            await session.commit()

    # ==================== !ТРЕКИ ====================
    if cmd == "!ТРЕКИ":
        tracks = _get_tracks(user_state)
        if not tracks:
            await message.answer(
                "📋 <b>Треки</b>\n\n"
                "У тебя пока нет активных треков.\n"
                "Добавь: <code>!ТРЕК ДОБАВИТЬ Название</code>\n\n"
                "💡 Примеры треков:\n"
                "• Строительство/МОК\n"
                "• Карьера/Вахта\n"
                "• Инвестиции\n"
                "• Корея/TOPIK\n"
                "• ИИ и технологии/Обучение\n"
                "• Психология/Дисциплина"
            )
            return

        text = "📋 <b>Твои треки:</b>\n\n"
        active = [t for t in tracks if t.get("status") == "active"]
        paused = [t for t in tracks if t.get("status") == "paused"]

        for t in active:
            text += f"🟢 <b>{t['name']}</b>\n"
        for t in paused:
            text += f"⏸ <b>{t['name']}</b> (на паузе)\n"

        text += f"\n📊 Всего: {len(tracks)} | 🟢 Активных: {len(active)} | ⏸ Пауза: {len(paused)}"
        await message.answer(text)
        return

    # ==================== !ТРЕК ДОБАВИТЬ ====================
    if cmd == "!ТРЕК" and len(parts) >= 3 and parts[1].upper() == "ДОБАВИТЬ":
        name = parts[2].strip()
        tracks = _get_tracks(user_state)

        if any(t["name"].lower() == name.lower() for t in tracks):
            await message.answer(f"⚠️ Трек «{name}» уже есть в списке.")
            return

        tracks.append({"name": name, "status": "active", "hours": 0.0, "goal_hours": 0.0})
        _save_tracks(user_state, tracks)

        async with async_session() as session:
            await session.commit()

        await message.answer(
            f"✅ Трек «<b>{name}</b>» добавлен!\n\n"
            f"Всего треков: {len(tracks)}\n"
            f"Смотри: <code>!ТРЕКИ</code>"
        )
        return

    # ==================== !ТРЕК УДАЛИТЬ ====================
    if cmd == "!ТРЕК" and len(parts) >= 3 and parts[1].upper() == "УДАЛИТЬ":
        name = parts[2].strip()
        tracks = _get_tracks(user_state)
        new_tracks = [t for t in tracks if t["name"].lower() != name.lower()]

        if len(new_tracks) == len(tracks):
            await message.answer(f"❌ Трек «{name}» не найден.\n\nСмотри: <code>!ТРЕКИ</code>")
            return

        _save_tracks(user_state, new_tracks)

        async with async_session() as session:
            await session.commit()

        await message.answer(f"🗑 Трек «<b>{name}</b>» удалён.")
        return

    # ==================== !ТРЕК ПАУЗА ====================
    if cmd == "!ТРЕК" and len(parts) >= 3 and parts[1].upper() == "ПАУЗА":
        name = parts[2].strip()
        tracks = _get_tracks(user_state)

        found = False
        for t in tracks:
            if t["name"].lower() == name.lower():
                t["status"] = "paused"
                found = True
                break

        if not found:
            await message.answer(f"❌ Трек «{name}» не найден.")
            return

        _save_tracks(user_state, tracks)

        async with async_session() as session:
            await session.commit()

        await message.answer(f"⏸ Трек «<b>{name}</b>» поставлен на паузу.")
        return

    # ==================== !ПРОГРЕСС (заглушка) ====================
    if cmd == "!ПРОГРЕСС":
        tracks = _get_tracks(user_state)
        active = [t for t in tracks if t.get("status") == "active"]
        paused = [t for t in tracks if t.get("status") == "paused"]

        if not tracks:
            await message.answer(
                "📊 <b>Прогресс</b>\n\n"
                "У тебя пока нет треков.\n"
                "Добавь первый: <code>!ТРЕК ДОБАВИТЬ Название</code>"
            )
            return

        text = "📊 <b>Прогресс по трекам</b>\n\n"
        for t in active:
            text += f"🟢 <b>{t['name']}</b>\n"
        for t in paused:
            text += f"⏸ <b>{t['name']}</b>\n"

        text += f"\n📈 Всего: {len(tracks)} | Активных: {len(active)} | На паузе: {len(paused)}"
        text += "\n\n💡 Подробный дашборд в разработке."
        await message.answer(text)
        return

    # ==================== !ВРЕМЯ (заглушка) ====================
    if cmd == "!ВРЕМЯ":
        await message.answer(
            "⏱ <b>!ВРЕМЯ</b>\n\n"
            "Формат: <code>!ВРЕМЯ [название трека] [часы]</code>\n"
            "Пример: <code>!ВРЕМЯ Корея/TOPIK 2</code>\n\n"
            "⚠️ Полный функционал счётчика часов — в разработке."
        )
        return

    # ==================== РЕЖИМЫ ОТВЕТА ====================
    if cmd == "!ЖМИ":
        await _set_response_mode(message, "short")
        return
    if cmd == "!РАЗВЕРНИ":
        await _set_response_mode(message, "long")
        return

    # ==================== !ФОКУС ====================
    if cmd == "!ФОКУС":
        topic = parts[1] if len(parts) > 1 else ""
        if not topic:
            await message.answer(
                "🎯 <b>!ФОКУС</b>\n\n"
                "Укажи тему:\n"
                "<code>!ФОКУС [тема]</code>\n\n"
                "Пример: <code>!ФОКУС Корея</code>"
            )
            return
        await _set_focus(message, topic)
        return

    # ==================== !СБРОС ====================
    if cmd == "!СБРОС":
        await _reset_settings(message)
        return

    # ==================== НЕИЗВЕСТНАЯ КОМАНДА ====================
    await message.answer(
        f"❓ Неизвестная команда: <code>{message.text[:30]}</code>\n\n"
        f"📋 <b>Доступные !-команды:</b>\n"
        f"<code>!ТРЕКИ</code> — список треков\n"
        f"<code>!ТРЕК ДОБАВИТЬ Название</code>\n"
        f"<code>!ТРЕК УДАЛИТЬ Название</code>\n"
        f"<code>!ТРЕК ПАУЗА Название</code>\n"
        f"<code>!ПРОГРЕСС</code> — прогресс по трекам\n"
        f"<code>!ВРЕМЯ [трек] [часы]</code>\n"
        f"<code>!ЖМИ</code> — сжатый ответ\n"
        f"<code>!РАЗВЕРНИ</code> — подробный ответ\n"
        f"<code>!ФОКУС [тема]</code> — приоритет темы\n"
        f"<code>!СБРОС</code> — сброс настроек\n\n"
        f"🎛 Или используй кнопки: <code>/system</code>"
    )

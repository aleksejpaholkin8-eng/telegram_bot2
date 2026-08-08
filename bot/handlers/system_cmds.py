from aiogram import Router, types, F
from sqlalchemy import select

from db.database import async_session
from db.models import UserState
from bot.handlers.tracks import _get_tracks, _save_tracks

router = Router()


async def _set_response_mode(message: types.Message, mode: str):
    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == message.from_user.id)
        )
        us = result.scalar_one_or_none()
        if not us:
            us = UserState(user_id=message.from_user.id, json_passport={"response_mode": mode}, tracks=[], counters={})
            session.add(us)
        else:
            passport = us.json_passport or {}
            passport["response_mode"] = mode
            us.json_passport = passport
        await session.commit()

    mode_text = "📄 Сжатый" if mode == "short" else "📖 Развёрнутый"
    await message.answer(f"✅ Режим ответа: <b>{mode_text}</b>\n\nСледующий запрос к AI будет в этом формате.\nСбросить: <code>!СБРОС</code>")


async def _set_focus(message: types.Message, topic: str):
    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == message.from_user.id)
        )
        us = result.scalar_one_or_none()
        if not us:
            us = UserState(user_id=message.from_user.id, json_passport={"focus": topic}, tracks=[], counters={})
            session.add(us)
        else:
            passport = us.json_passport or {}
            passport["focus"] = topic
            us.json_passport = passport
        await session.commit()

    await message.answer(
        f"🎯 <b>Фокус установлен:</b> <i>{topic}</i>\n\n"
        "AI будет приоритизировать эту тему.\n"
        "Сбросить: <code>!СБРОС</code>"
    )


async def _reset_settings(message: types.Message):
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


@router.message(F.text.startswith("!"))
async def system_commands(message: types.Message):
    text = message.text.strip()
    parts = text.split(maxsplit=2)
    cmd = parts[0].upper()

    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == message.from_user.id)
        )
        user_state = result.scalar_one_or_none()
        if not user_state:
            user_state = UserState(user_id=message.from_user.id, tracks=[], json_passport={}, counters={})
            session.add(user_state)
            await session.commit()

    if cmd == "!ТРЕКИ":
        tracks = _get_tracks(user_state)
        if not tracks:
            await message.answer(
                "📋 <b>Треки</b>\n\n"
                "У тебя пока нет активных треков.\n"
                "Добавь: <code>!ТРЕК ДОБАВИТЬ Название</code>\n\n"
                "💡 Примеры:\n"
                "• Строительство/МОК\n"
                "• Карьера/Вахта\n"
                "• Инвестиции\n"
                "• Корея/TOPIK\n"
                "• ИИ и технологии/Обучение\n"
                "• Психология/Дисциплина"
            )
            return

        active = [t for t in tracks if t.get("status") == "active"]
        paused = [t for t in tracks if t.get("status") == "paused"]
        text = "📋 <b>Твои треки:</b>\n\n"
        for t in active:
            text += f"🟢 <b>{t['name']}</b>\n"
        for t in paused:
            text += f"⏸ <b>{t['name']}</b> (на паузе)\n"
        text += f"\n📊 Всего: {len(tracks)} | 🟢 Активных: {len(active)} | ⏸ Пауза: {len(paused)}"
        await message.answer(text)
        return

    if cmd == "!ТРЕК" and len(parts) >= 3 and parts[1].upper() == "ДОБАВИТЬ":
        name = parts[2].strip()
        tracks = _get_tracks(user_state)
        if any(t["name"].lower() == name.lower() for t in tracks):
            await message.answer(f"⚠️ Трек «{name}» уже есть.")
            return
        tracks.append({"name": name, "status": "active", "hours": 0.0, "goal_hours": 0.0})
        _save_tracks(user_state, tracks)
        async with async_session() as session:
            await session.commit()
        await message.answer(f"✅ Трек «<b>{name}</b>» добавлен!\n\nВсего треков: {len(tracks)}\nСмотри: <code>!ТРЕКИ</code>")
        return

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

    if cmd == "!ПРОГРЕСС":
        tracks = _get_tracks(user_state)
        active = [t for t in tracks if t.get("status") == "active"]
        paused = [t for t in tracks if t.get("status") == "paused"]
        if not tracks:
            await message.answer("📊 <b>Прогресс</b>\n\nУ тебя пока нет треков.\nДобавь первый: <code>!ТРЕК ДОБАВИТЬ Название</code>")
            return
        text = "📊 <b>Прогресс по трекам</b>\n\n"
        for t in active:
            text += f"🟢 <b>{t['name']}</b>\n"
        for t in paused:
            text += f"⏸ <b>{t['name']}</b>\n"
        text += f"\n📈 Всего: {len(tracks)} | Активных: {len(active)} | На паузе: {len(paused)}\n\n💡 Подробный дашборд в разработке."
        await message.answer(text)
        return

    if cmd == "!ВРЕМЯ":
        words = text.split()
        # Минимум 3 слова: !ВРЕМЯ + название + число
        if len(words) < 3:
            await message.answer(
                "⏱ <b>!ВРЕМЯ</b>\n\n"
                "Формат: <code>!ВРЕМЯ [название трека] [часы]</code>\n"
                "Пример: <code>!ВРЕМЯ Корея/TOPIK 2</code>\n"
                "Пример: <code>!ВРЕМЯ Строительство МОК 1.5</code>"
            )
            return

        # Последнее слово — часы (можно дробное: 1.5)
        try:
            hours = float(words[-1])
        except ValueError:
            await message.answer(
                "❌ Последнее слово должно быть числом часов.\n"
                "Пример: <code>!ВРЕМЯ Корея/TOPIK 2</code>"
            )
            return

        # Всё посередине — название трека
        track_name = " ".join(words[1:-1]).strip()
        if not track_name:
            await message.answer("❌ Укажи название трека.")
            return

        tracks = _get_tracks(user_state)
        track_found = None

        # 1) Точное совпадение
        for t in tracks:
            if t["name"].lower() == track_name.lower():
                track_found = t
                break

        # 2) Частичное совпадение (если точного нет)
        if not track_found:
            for t in tracks:
                if track_name.lower() in t["name"].lower() or t["name"].lower() in track_name.lower():
                    track_found = t
                    break

        if not track_found:
            await message.answer(
                f"❌ Трек «{track_name}» не найден.\n\n"
                f"Смотри список: <code>!ТРЕКИ</code>"
            )
            return

        # Прибавляем часы
        old_hours = track_found.get("hours", 0.0)
        track_found["hours"] = old_hours + hours
        _save_tracks(user_state, tracks)

        async with async_session() as session:
            await session.commit()

        await message.answer(
            f"⏱ <b>Трек «{track_found['name']}»</b>\n\n"
            f"Добавлено: <b>+{hours}ч</b>\n"
            f"Всего: <b>{track_found['hours']}ч</b>"
        )
        return

    if cmd == "!ЖМИ":
        await _set_response_mode(message, "short")
        return
    if cmd == "!РАЗВЕРНИ":
        await _set_response_mode(message, "long")
        return

    if cmd == "!ФОКУС":
        topic = parts[1] if len(parts) > 1 else ""
        if not topic:
            await message.answer("🎯 <b>!ФОКУС</b>\n\nУкажи тему:\n<code>!ФОКУС [тема]</code>\n\nПример: <code>!ФОКУС Корея</code>")
            return
        await _set_focus(message, topic)
        return

    if cmd == "!СБРОС":
        await _reset_settings(message)
        return

    await message.answer(
        f"❓ Неизвестная команда: <code>{message.text[:30]}</code>\n\n"
        "📋 <b>Доступные !-команды:</b>\n"
        "<code>!ТРЕКИ</code> — список треков\n"
        "<code>!ТРЕК ДОБАВИТЬ Название</code>\n"
        "<code>!ТРЕК УДАЛИТЬ Название</code>\n"
        "<code>!ТРЕК ПАУЗА Название</code>\n"
        "<code>!ПРОГРЕСС</code> — прогресс по трекам\n"
        "<code>!ВРЕМЯ [трек] [часы]</code>\n"
        "<code>!ЖМИ</code> — сжатый ответ\n"
        "<code>!РАЗВЕРНИ</code> — подробный ответ\n"
        "<code>!ФОКУС [тема]</code> — приоритет темы\n"
        "<code>!СБРОС</code> — сброс настроек\n\n"
        "🎛 Или используй кнопки: <code>/system</code>"
    )

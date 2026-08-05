from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from bot.handlers.common import get_or_create_user
from db.database import async_session
from db.models import User, Role, Command as CommandModel, UserState, RoleTariffAccess
from services.llm_service import ask_llm, get_api_key
from services.tariff_service import check_token_limit, check_feature_access
from services.role_router import select_roles
from services.prompt_builder import build_system_prompt, count_tokens
from services.search_service import web_search

router = Router()


# ============ /ROLES ============

@router.message(Command(commands="roles"))
async def cmd_roles(message: types.Message):
    user = await get_or_create_user(message)

    async with async_session() as session:
        access_result = await session.execute(
            select(RoleTariffAccess).where(RoleTariffAccess.tariff == user.tariff).limit(1)
        )
        has_records = access_result.scalar_one_or_none() is not None

        if has_records:
            result = await session.execute(
                select(Role).join(
                    RoleTariffAccess,
                    Role.id == RoleTariffAccess.role_id
                ).where(
                    Role.is_active == True,
                    RoleTariffAccess.tariff == user.tariff,
                    RoleTariffAccess.access == True
                )
            )
            roles = result.scalars().all()
        else:
            # Fallback на старую логику
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

        # Пагинация: разбиваем на чанки по 15 ролей
        chunk_size = 15
        if len(roles) == 0:
            await message.answer(
                f"🎭 <b>Роли (тариф: {user.tariff.upper()}):</b>\n\nНет доступных ролей."
            )
            return

        for i in range(0, len(roles), chunk_size):
            chunk = roles[i:i + chunk_size]
            text = f"🎭 <b>Роли {i+1}-{i+len(chunk)} из {len(roles)}</b> (тариф: {user.tariff.upper()})\n\n"
            for role in chunk:
                icon = "🆓" if role.tier_access == "lite" else "💎"
                text += f"{icon} <b>{role.name}</b>\n"
                text += f"   🔑 {role.keywords}\n\n"
            await message.answer(text)


# ============ /COMMANDS ============

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

        chunk_size = 20
        if len(commands) == 0:
            await message.answer(
                f"⌨️ <b>Команды (тариф: {user.tariff.upper()}):</b>\n\nНет доступных команд."
            )
            return

        for i in range(0, len(commands), chunk_size):
            chunk = commands[i:i + chunk_size]
            text = f"⌨️ <b>Команды {i+1}-{i+len(chunk)} из {len(commands)}</b> (тариф: {user.tariff.upper()})\n\n"
            for cmd in chunk:
                icon = "✅" if cmd.tier_access == "lite" else "🔒"
                text += f"{icon} <b>{cmd.name}</b> — {cmd.description}\n"
            await message.answer(text)


# ============ /SEARCH ============

@router.message(Command(commands="search"))
async def cmd_search(message: types.Message):
    user = await get_or_create_user(message)

    has_access, _ = await check_feature_access(user.tariff, "web_search")
    if not has_access:
        await message.answer(
            "🔒 <b>Веб-поиск недоступен</b>\n\n"
            f"В тарифе {user.tariff.upper()} эта функция отключена.\n"
            "Обнови до Pro или Business: /admin (если ты владелец)"
        )
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "🔍 <b>Поиск в интернете</b>\n\n"
            "Формат: <code>/search запрос</code>\n"
            "Пример: <code>/search python asyncio tutorial</code>\n\n"
            "💡 Результаты будут включены в ответ AI."
        )
        return

    query = args[1]
    wait_msg = await message.answer(f"🔍 Ищу: <i>{query}</i>...")

    results, error = await web_search(query, max_results=5)

    if error:
        await wait_msg.edit_text(error)
        return

    text = f"🔍 <b>Результаты поиска:</b> <i>{query}</i>\n\n"
    for i, r in enumerate(results, 1):
        text += f"{i}. <b>{r['title']}</b>\n"
        text += f"   {r['snippet'][:150]}...\n"
        text += f"   <a href='{r['url']}'>Ссылка</a>\n\n"

    if len(text) > 4000:
        parts = []
        current = f"🔍 <b>Результаты поиска:</b> <i>{query}</i>\n\n"
        for i, r in enumerate(results, 1):
            block = (
                f"{i}. <b>{r['title']}</b>\n"
                f"   {r['snippet'][:150]}...\n"
                f"   <a href='{r['url']}'>Ссылка</a>\n\n"
            )
            if len(current) + len(block) > 4000:
                parts.append(current)
                current = block
            else:
                current += block
        if current:
            parts.append(current)

        await wait_msg.delete()
        for part in parts:
            await message.answer(part, disable_web_page_preview=True)
    else:
        await wait_msg.edit_text(text, disable_web_page_preview=True)


# ============ /SEARCHAI ============

@router.message(Command(commands="searchai"))
async def cmd_searchai(message: types.Message):
    user = await get_or_create_user(message)

    has_access, _ = await check_feature_access(user.tariff, "web_search")
    if not has_access:
        await message.answer(
            "🔒 <b>Поиск + AI недоступен</b>\n\n"
            f"В тарифе {user.tariff.upper()} веб-поиск отключён.\n"
            "Админ может включить через /admin → ⚙️ Фичи тарифа."
        )
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "🔍 <b>Поиск + AI</b>\n\n"
            "Формат: <code>/searchai запрос</code>\n"
            "Примеры:\n"
            "<code>/searchai актуальные зарплаты python разработчик</code>\n"
            "<code>/searchai новости DeepSeek 2026</code>\n\n"
            "Бот найдёт информацию и даст развёрнутый ответ через AI с указанием источников."
        )
        return

    query = args[1]
    wait_msg = await message.answer(f"🔍 Ищу в интернете: <i>{query}</i>...")

    results, error = await web_search(query, max_results=5)

    if error:
        await wait_msg.edit_text(
            f"❌ <b>Поиск не удался</b>\n\n{error}\n\n"
            f"Попробуй позже или задай вопрос без поиска — просто напиши текст."
        )
        return

    search_context = "\n\n=== РЕЗУЛЬТАТЫ ПОИСКА В ИНТЕРНЕТЕ ===\n"
    for i, r in enumerate(results, 1):
        search_context += f"{i}. {r['title']}\n{r['snippet'][:400]}\nИсточник: {r['url']}\n\n"
    search_context += "=== КОНЕЦ ПОИСКА ===\n"

    await wait_msg.edit_text(f"🔍 Найдено {len(results)} результатов. Анализирую через AI...")

    _, max_roles = await check_feature_access(user.tariff, "max_roles")
    if max_roles == 0:
        max_roles = 5

    selected_roles = await select_roles(message.from_user.id, query, max_roles=max_roles)
    base_prompt = await build_system_prompt(message.from_user.id, selected_roles)

    system_prompt = (
        base_prompt + "\n\n" +
        search_context +
        "\nИНСТРУКЦИЯ ДЛЯ AI: Ответь на вопрос пользователя, используя информацию из результатов поиска выше. "
        "Если информации недостаточно — скажи об этом. В конце ответа перечисли источники (номера)."
    )

    default_model = "groq/llama-3.3-70b-versatile"
    provider = default_model.split("/")[0]

    api_key, source = await get_api_key(message.from_user.id, provider=provider)
    if not api_key:
        await message.answer("🔑 Нет API-ключа для AI.")
        return

    answer, success = await ask_llm(
        prompt=query,
        user_id=message.from_user.id,
        model=default_model,
        system_prompt=system_prompt,
        max_tokens=1500
    )

    if success:
        # Считаем токены (включая search_context!)
        try:
            tokens_used = (
                count_tokens(query) +
                count_tokens(answer) +
                count_tokens(search_context) +
                count_tokens(system_prompt)
            )
            async with async_session() as session:
                result = await session.execute(
                    select(UserState).where(UserState.user_id == message.from_user.id)
                )
                us = result.scalar_one_or_none()
                if us:
                    counters = us.counters or {}
                    counters["daily_tokens"] = counters.get("daily_tokens", 0) + tokens_used
                    us.counters = counters
                    await session.commit()
        except Exception:
            pass

        sources = "\n\n📚 <b>Источники:</b>\n"
        for i, r in enumerate(results[:3], 1):
            sources += f"{i}. <a href='{r['url']}'>{r['title'][:60]}</a>\n"

        full_text = f"🔍 <b>Ответ AI (с поиском):</b>\n\n{answer}{sources}"

        if len(full_text) > 4000:
            await wait_msg.delete()
            parts = [answer[i:i + 3800] for i in range(0, len(answer), 3800)]
            for idx, part in enumerate(parts):
                prefix = f"🔍 <b>Ответ AI (часть {idx+1}/{len(parts)}):</b>\n\n"
                await message.answer(prefix + part, disable_web_page_preview=True)
            await message.answer(sources, disable_web_page_preview=True)
        else:
            await wait_msg.edit_text(full_text, disable_web_page_preview=True)
    else:
        await wait_msg.edit_text(f"❌ <b>Ошибка AI:</b>\n\n{answer}")


# ============ SMART HANDLER (ГЛАВНЫЙ ОБРАБОТЧИК) ============

# ← ИСПРАВЛЕНИЕ: StateFilter(None) = срабатывает ТОЛЬКО когда нет FSM-состояния
# Это предотвращает перехват сообщений во время диалогов (регистрация, треки, BYOK)
@router.message(StateFilter(None))
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

    # --- Проверяем наличие ключа ---
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

    _, max_roles = await check_feature_access(user.tariff, "max_roles")
    if max_roles == 0:
        max_roles = 5

    selected_roles = await select_roles(
        message.from_user.id, message.text, max_roles=max_roles
    )
    system_prompt = await build_system_prompt(message.from_user.id, selected_roles)

    # --- Проверяем пользовательские настройки (!ЖМИ, !РАЗВЕРНИ, !ФОКУС) ---
    response_mode = "normal"
    focus_topic = ""
    async with async_session() as session:
        result = await session.execute(
            select(UserState).where(UserState.user_id == message.from_user.id)
        )
        us = result.scalar_one_or_none()
        if us and us.json_passport:
            response_mode = us.json_passport.get("response_mode", "normal")
            focus_topic = us.json_passport.get("focus", "")

    # Модифицируем промпт под режим
    if response_mode == "short":
        system_prompt += (
            "\n\n[РЕЖИМ: КРАТКО] Ответь максимально сжато: 3-5 тезисов, "
            "без вступлений и заключений."
        )
        max_tokens = 500
    elif response_mode == "long":
        system_prompt += (
            "\n\n[РЕЖИМ: ПОДРОБНО] Ответь максимально развёрнуто, "
            "с примерами и деталями."
        )
        max_tokens = 2000
    else:
        max_tokens = 1000

    if focus_topic:
        system_prompt += f"\n\n[ФОКУС: {focus_topic}] Приоритет этой теме. Адаптируй ответ."

    roles_names = ", ".join([r.name.split(":")[0] for r in selected_roles[:3]])
    try:
        await wait_msg.edit_text(
            f"⚡ Активированы роли: {roles_names}\n⏳ Думаю..."
        )
    except Exception:
        pass

    # --- ОТПРАВЛЯЕМ В AI ---
    answer, success = await ask_llm(
        prompt=message.text,
        user_id=message.from_user.id,
        model=default_model,
        system_prompt=system_prompt,
        max_tokens=max_tokens
    )

    # --- Показываем ответ и обновляем счётчик токенов ---
    if success:
        try:
            tokens_used = (
                count_tokens(message.text) +
                count_tokens(answer) +
                count_tokens(system_prompt)
            )
            async with async_session() as session:
                result = await session.execute(
                    select(UserState).where(UserState.user_id == message.from_user.id)
                )
                us = result.scalar_one_or_none()
                if us:
                    counters = us.counters or {}
                    counters["daily_tokens"] = counters.get("daily_tokens", 0) + tokens_used
                    us.counters = counters
                    await session.commit()
        except Exception:
            pass

        source_icon = "🔑" if source == "byok" else "⚡"
        roles_info = (
            f"\n\n<i>🎭 Активные роли: {roles_names}</i>"
            if selected_roles else ""
        )

        full_text = f"{source_icon} <b>Ответ AI:</b>\n\n{answer}{roles_info}"

        # Удаляем wait_msg перед отправкой ответа
        try:
            await wait_msg.delete()
        except Exception:
            pass

        if len(full_text) > 4000:
            parts = [answer[i:i + 4000] for i in range(0, len(answer), 4000)]
            for idx, part in enumerate(parts):
                prefix = (
                    f"{source_icon} <b>Ответ AI (часть {idx+1}/{len(parts)}):</b>\n\n"
                )
                suffix = roles_info if idx == len(parts) - 1 else ""
                await message.answer(f"{prefix}{part}{suffix}")
        else:
            await message.answer(full_text)
    else:
        # Удаляем wait_msg и при ошибке
        try:
            await wait_msg.delete()
        except Exception:
            pass
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{answer}")

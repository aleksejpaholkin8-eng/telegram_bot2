# ============================================
# ОБРАБОТЧИКИ (ЭТАП 5.4 — /admin панель + багфиксы)
# ============================================

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.states import UserRegistration, ByokInput, UploadPrompt, AdminEditLimit, TrackMenu
from db.database import async_session
from db.models import User, Role, Command as CommandModel, UserState, UserApiKey, TariffFeature, RoleTariffAccess
from sqlalchemy import select

from services.llm_service import ask_llm, get_api_key
from services.tariff_service import check_token_limit, check_feature_access
from services.role_router import select_roles
from services.prompt_builder import build_system_prompt, count_tokens
from services.encryption import encrypt_key
from services.search_service import web_search

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
                tariff="lite"
            )
            session.add(user)
            await session.commit()
        
        return user


# ============ ОБЫЧНЫЕ КОМАНДЫ (без изменений) ============

@router.message(Command(commands="start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    
    user = await get_or_create_user(message)
    
    # ← НОВОЕ: если владелец — показываем админ-кнопку под полем ввода
    from config.settings import settings
    if message.from_user.id == settings.owner_id:
        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
        admin_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🔧 Админ-меню")]],
            resize_keyboard=True
        )
        await message.answer(
            f"👋 <b>Привет, владелец!</b>\n\n"
            f"🎫 Твой тариф: <b>{user.tariff.upper()}</b>\n\n"
            f"📋 Команды:\n"
            f"/start — начало\n"
            f"/help — справка\n"
            f"/register — регистрация\n"
            f"/roles — доступные роли\n"
            f"/commands — доступные команды\n"
            f"/setkey — добавить свой API-ключ (BYOK)\n"
            f"/admin — настройка тарифов\n"
            f"/upload_prompt — загрузить промпт\n"
            f"/settariff — сменить свой тариф\n\n"
            f"💡 Просто напиши сообщение — и я отвечу через AI.",
            reply_markup=admin_kb
        )
        return
    
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
        "• /search [запрос] — поиск в интернете (Pro/Business)\n"
        "• /searchai [запрос] — поиск в интернете + ответ AI (Pro/Business)\n"
        "\n📋 <b>!-Команды системы:</b>\n"
        "• !ТРЕКИ — список треков\n"
        "• !ТРЕК ДОБАВИТЬ [название]\n"
        "• !ТРЕК УДАЛИТЬ [название]\n"
        "• !ТРЕК ПАУЗА [название]\n"
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
    from config.settings import settings
    
    async with async_session() as session:
               # Обычная логика для пользователей
        # ← НОВОЕ: фильтруем через RoleTariffAccess, если админ уже настраивал
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
            # Fallback на старую логику (если админ ещё не настраивал)
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
            return
        
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

                # ← НОВОЕ: разбиваем на чанки, чтобы не превысить лимит 4096 символов
        chunk_size = 15
        if len(roles) == 0:
            await message.answer(f"🎭 <b>Роли (тариф: {user.tariff.upper()}):</b>\n\nНет доступных ролей.")
            return
            
        for i in range(0, len(roles), chunk_size):
            chunk = roles[i:i+chunk_size]
            text = f"🎭 <b>Роли {i+1}-{i+len(chunk)} из {len(roles)}</b> (тариф: {user.tariff.upper()})\n\n"
            for role in chunk:
                icon = "🆓" if role.tier_access == "lite" else "💎"
                text += f"{icon} <b>{role.name}</b>\n"
                text += f"   🔑 {role.keywords}\n\n"
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

        chunk_size = 20
        if len(commands) == 0:
            await message.answer(f"⌨️ <b>Команды (тариф: {user.tariff.upper()}):</b>\n\nНет доступных команд.")
            return
            
        for i in range(0, len(commands), chunk_size):
            chunk = commands[i:i+chunk_size]
            text = f"⌨️ <b>Команды {i+1}-{i+len(chunk)} из {len(commands)}</b> (тариф: {user.tariff.upper()})\n\n"
            for cmd in chunk:
                icon = "✅" if cmd.tier_access == "lite" else "🔒"
                text += f"{icon} <b>{cmd.name}</b> — {cmd.description}\n"
            await message.answer(text)
            

@router.message(Command(commands="search"))
async def cmd_search(message: types.Message):
    """
    Поиск в интернете. Доступен только в Pro/Business.
    Формат: /search запрос
    """
    user = await get_or_create_user(message)
    
    # Проверяем доступность функции в тарифе
    has_access, _ = await check_feature_access(user.tariff, "web_search")
    if not has_access:
        await message.answer(
            "🔒 <b>Веб-поиск недоступен</b>\n\n"
            f"В тарифе {user.tariff.upper()} эта функция отключена.\n"
            "Обнови до Pro или Business: /admin (если ты владелец)"
        )
        return
    
    # Парсим запрос
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
    
    # Формируем красивый ответ
    text = f"🔍 <b>Результаты поиска:</b> <i>{query}</i>\n\n"
    for i, r in enumerate(results, 1):
        text += f"{i}. <b>{r['title']}</b>\n"
        text += f"   {r['snippet'][:150]}...\n"
        text += f"   <a href='{r['url']}'>Ссылка</a>\n\n"
    
    # Разбиваем, если длинно
    if len(text) > 4000:
        parts = []
        current = f"🔍 <b>Результаты поиска:</b> <i>{query}</i>\n\n"
        for i, r in enumerate(results, 1):
            block = f"{i}. <b>{r['title']}</b>\n   {r['snippet'][:150]}...\n   <a href='{r['url']}'>Ссылка</a>\n\n"
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

@router.message(Command(commands="searchai"))
async def cmd_searchai(message: types.Message):
    """
    Поиск в интернете + ответ AI на основе найденной информации.
    Доступно в Pro/Business.
    """
    user = await get_or_create_user(message)
    
    # Проверяем, включён ли веб-поиск в тарифе
    has_access, _ = await check_feature_access(user.tariff, "web_search")
    if not has_access:
        await message.answer(
            "🔒 <b>Поиск + AI недоступен</b>\n\n"
            f"В тарифе {user.tariff.upper()} веб-поиск отключён.\n"
            "Админ может включить через /admin → ⚙️ Фичи тарифа."
        )
        return
    
    # Парсим запрос
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
    
    # --- 1. ПОИСК ---
    results, error = await web_search(query, max_results=5)
    
    if error:
        await wait_msg.edit_text(
            f"❌ <b>Поиск не удался</b>\n\n{error}\n\n"
            f"Попробуй позже или задай вопрос без поиска — просто напиши текст."
        )
        return
    
    # --- 2. ФОРМИРУЕМ КОНТЕКСТ ПОИСКА ---
    search_context = "\n\n=== РЕЗУЛЬТАТЫ ПОИСКА В ИНТЕРНЕТЕ ===\n"
    for i, r in enumerate(results, 1):
        search_context += f"{i}. {r['title']}\n{r['snippet'][:400]}\nИсточник: {r['url']}\n\n"
    search_context += "=== КОНЕЦ ПОИСКА ===\n"
    
    await wait_msg.edit_text(f"🔍 Найдено {len(results)} результатов. Анализирую через AI...")
    
    # --- 3. ВЫБИРАЕМ РОЛИ И СОБИРАЕМ ПРОМПТ ---
    _, max_roles = await check_feature_access(user.tariff, "max_roles")
    if max_roles == 0:
        max_roles = 5
        
    selected_roles = await select_roles(message.from_user.id, query, max_roles=max_roles)
    base_prompt = await build_system_prompt(message.from_user.id, selected_roles)
    
    # Добавляем результаты поиска к системному промпту
    system_prompt = (
        base_prompt + "\n\n" +
        search_context +
        "\nИНСТРУКЦИЯ ДЛЯ AI: Ответь на вопрос пользователя, используя информацию из результатов поиска выше. "
        "Если информации недостаточно — скажи об этом. В конце ответа перечисли источники (номера)."
    )
    
    # --- 4. ОТПРАВЛЯЕМ В AI ---
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
    
    # --- 5. ПОКАЗЫВАЕМ ОТВЕТ ---
    if success:
        # Считаем токены (включая поисковый контекст)
        try:
            tokens_used = count_tokens(query) + count_tokens(answer) + count_tokens(search_context)
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
        
        # Формируем источники
        sources = "\n\n📚 <b>Источники:</b>\n"
        for i, r in enumerate(results[:3], 1):
            sources += f"{i}. <a href='{r['url']}'>{r['title'][:60]}</a>\n"
        
        full_text = f"🔍 <b>Ответ AI (с поиском):</b>\n\n{answer}{sources}"
        
        # Разбиваем, если длинно
        if len(full_text) > 4000:
            await wait_msg.delete()
            parts = [answer[i:i+3800] for i in range(0, len(answer), 3800)]
            for idx, part in enumerate(parts):
                prefix = f"🔍 <b>Ответ AI (часть {idx+1}/{len(parts)}):</b>\n\n"
                await message.answer(prefix + part, disable_web_page_preview=True)
            await message.answer(sources, disable_web_page_preview=True)
        else:
            await wait_msg.edit_text(full_text, disable_web_page_preview=True)
    else:
        await wait_msg.edit_text(f"❌ <b>Ошибка AI:</b>\n\n{answer}")


@router.message(Command(commands="settariff"))
async def cmd_settariff(message: types.Message):
    from config.settings import settings
    
    if message.from_user.id != settings.owner_id:
        await message.answer("⛔ Эта команда только для владельца бота.")
        return
    
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


# ============ /upload_prompt (ИЗМЕНЕНО — добавлен FSM) ============

@router.message(Command(commands="upload_prompt"))
async def cmd_upload_prompt(message: types.Message, state: FSMContext):
    from config.settings import settings
    
    if message.from_user.id != settings.owner_id:
        await message.answer("⛔ Эта команда только для владельца бота.")
        return
    
    # ← НОВОЕ: ставим бота в состояние "жду файл/текст"
    await state.set_state(UploadPrompt.waiting_for_file)
    
    await message.answer(
        "📤 <b>Загрузка нового промпта</b>\n\n"
        "Отправь мне файл <code>.md</code> (Промпт 1) или вставь его текст сообщением.\n\n"
        "⚠️ <b>Важно:</b>\n"
        "• Пользовательские данные (треки, паспорт, тариф) сохранятся\n"
        "• Существующие роли обновятся, новые добавятся\n"
        "• Для отмены напиши /start\n\n"
        "Жду файл или текст..."
    )


@router.message(F.document)
async def handle_document_upload(message: types.Message, state: FSMContext):
    """
    Обрабатывает загруженный файл .md
    Теперь срабатывает ТОЛЬКО если бот ждёт файл (состояние UploadPrompt).
    """
    from config.settings import settings
    from parsers.prompt_parser import parse_prompt_text
    
    # ← НОВОЕ: проверяем, ждём ли мы файл
    current_state = await state.get_state()
    if current_state != UploadPrompt.waiting_for_file.state:
        return  # Игнорируем файлы в обычном режиме
    
    if message.from_user.id != settings.owner_id:
        return
    
    doc = message.document
    if not doc.file_name.endswith('.md'):
        await message.answer("❌ Нужен файл с расширением <code>.md</code>")
        return
    
    wait_msg = await message.answer("⏳ Скачиваю файл...")
    
    try:
        file = await message.bot.get_file(doc.file_id)
        file_content = await message.bot.download_file(file.file_path)
        text = file_content.read().decode('utf-8')
    except Exception as e:
        await wait_msg.edit_text(f"❌ Ошибка скачивания: {e}")
        await state.clear()
        return
    
    await wait_msg.edit_text("🔍 Парсю файл...")
    await _process_prompt_text(message, text, wait_msg, state)


# ← ИЗМЕНЕНО: добавлен фильтр состояния UploadPrompt.waiting_for_file
@router.message(F.text, ~F.text.startswith('/'), UploadPrompt.waiting_for_file)
async def handle_text_upload(message: types.Message, state: FSMContext):
    """
    Обрабатывает текст промпта, вставленный сообщением.
    Срабатывает ТОЛЬКО если бот в состоянии waiting_for_file.
    """
    from config.settings import settings
    from parsers.prompt_parser import parse_prompt_text
    
    if message.from_user.id != settings.owner_id:
        return
    
    if len(message.text) < 1000:
        await message.answer("❌ Слишком короткий текст для промпта. Минимум 1000 символов.")
        return
    
    wait_msg = await message.answer("🔍 Парсю текст...")
    await _process_prompt_text(message, message.text, wait_msg, state)


async def _process_prompt_text(message: types.Message, text: str, wait_msg: types.Message, state: FSMContext):
    """
    Общая логика: парсинг + дельта-обновление БД
    """
    from parsers.prompt_parser import parse_prompt_text
    from db.database import async_session
    from db.models import Role, Rule, Command
    from sqlalchemy import select
    
    try:
        parsed = parse_prompt_text(text)
    except Exception as e:
        await wait_msg.edit_text(f"❌ Ошибка парсинга: {e}")
        await state.clear()
        return
    
    if not parsed.roles and not parsed.rules:
        await wait_msg.edit_text(
            "❌ В файле не найдены роли или правила.\n\n"
            "Проверь формат файла. Ожидается структура Промпта 1."
        )
        await state.clear()
        return
    
    async with async_session() as session:
        added_roles = 0
        updated_roles = 0
        added_rules = 0
        updated_rules = 0
        added_cmds = 0
        updated_cmds = 0
        
        for role in parsed.roles:
            result = await session.execute(select(Role).where(Role.name == role.name))
            existing = result.scalar_one_or_none()
            
            if existing:
                existing.prompt_text = role.prompt_text
                existing.keywords = role.keywords
                existing.group_name = role.group_name
                existing.tier_access = role.tier_access
                existing.is_active = True
                updated_roles += 1
            else:
                session.add(Role(
                    name=role.name,
                    group_name=role.group_name,
                    prompt_text=role.prompt_text,
                    keywords=role.keywords,
                    tier_access=role.tier_access
                ))
                added_roles += 1
        
        for rule in parsed.rules:
            result = await session.execute(select(Rule).where(Rule.number == rule.number))
            existing = result.scalar_one_or_none()
            
            if existing:
                existing.text = rule.text
                updated_rules += 1
            else:
                session.add(Rule(number=rule.number, text=rule.text))
                added_rules += 1
        
        for cmd in parsed.commands:
            result = await session.execute(select(Command).where(Command.name == cmd.name))
            existing = result.scalar_one_or_none()
            
            if existing:
                existing.description = cmd.description
                existing.cluster = cmd.cluster
                existing.tier_access = cmd.tier_access
                updated_cmds += 1
            else:
                session.add(Command(
                    cluster=cmd.cluster,
                    name=cmd.name,
                    description=cmd.description,
                    tier_access=cmd.tier_access
                ))
                added_cmds += 1
        
        await session.commit()

            # --- СОЗДАЁМ ДЕФОЛТНЫЕ ДОСТУПЫ ДЛЯ РОЛЕЙ (если админ ещё не настраивал) ---
        for role in parsed.roles:
            result = await session.execute(select(Role).where(Role.name == role.name))
            db_role = result.scalar_one()
            
            for t in ["lite", "pro", "business"]:
                exists = await session.execute(
                    select(RoleTariffAccess).where(
                        RoleTariffAccess.role_id == db_role.id,
                        RoleTariffAccess.tariff == t
                    )
                )
                if not exists.scalar_one_or_none():
                    # Дефолт: business = True, остальное по tier_access
                    default_access = False
                    if t == "business":
                        default_access = True
                    elif t == "pro" and db_role.tier_access in ("lite", "pro"):
                        default_access = True
                    elif t == "lite" and db_role.tier_access == "lite":
                        default_access = True
                    
                    session.add(RoleTariffAccess(
                        role_id=db_role.id,
                        tariff=t,
                        access=default_access
                    ))
        await session.commit()
        # --- КОНЕЦ ---

    
    # ← НОВОЕ: очищаем состояние после обработки
    await state.clear()
    
    report = (
        f"✅ <b>Промпт загружен!</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"🎭 Роли: +{added_roles} новых, 🔄 {updated_roles} обновлено\n"
        f"📜 Правила: +{added_rules} новых, 🔄 {updated_rules} обновлено\n"
        f"⌨️ Команды: +{added_cmds} новых, 🔄 {updated_cmds} обновлено\n\n"
        f"💾 Пользовательские данные сохранены.\n"
        f"Проверь: /roles, /commands"
    )
    
    await wait_msg.edit_text(report)


# ============================================
# НОВОЕ: /admin ПАНЕЛЬ (ШАГ 5.4)
# ============================================

async def _send_admin_menu(target, user_id: int):
    """
    Универсальная функция показа админ-меню.
    target — либо message, либо callback (aiogram сам разберётся).
    user_id — ID пользователя (callback.from_user.id или message.from_user.id).
    """
    from config.settings import settings
    
    if user_id != settings.owner_id:
        if isinstance(target, types.Message):
            await target.answer("⛔ Эта команда только для владельца бота.")
        else:
            await target.answer("⛔ Нет доступа", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⚙️ Фичи тарифа", callback_data="admin:section:features")
    builder.button(text="🎭 Роли тарифа", callback_data="admin:section:roles")
    builder.button(text="📋 Админ-команды", callback_data="admin:commands")
    builder.adjust(1)
    
    text = "⚙️ <b>Админ-панель</b>\n\nВыбери раздел:"
    
    if isinstance(target, types.CallbackQuery):
        await target.message.edit_text(text, reply_markup=builder.as_markup())
    else:
        await target.answer(text, reply_markup=builder.as_markup())


@router.message(Command(commands="admin"))
async def cmd_admin(message: types.Message):
    """Команда /admin — показывает меню владельцу"""
    await _send_admin_menu(message, message.from_user.id)
    

@router.callback_query(F.data.startswith("admin:tariff:"))
async def admin_show_tariff(callback: types.CallbackQuery):
    """
    Показывает список фич выбранного тарифа с кнопками управления.
    """
    tariff = callback.data.split(":")[2]
    
    async with async_session() as session:
        result = await session.execute(
            select(TariffFeature).where(TariffFeature.tariff == tariff)
        )
        features = result.scalars().all()
    
    icon = "🆓" if tariff == "lite" else "⚡" if tariff == "pro" else "💎"
    text = f"{icon} <b>Настройки тарифа {tariff.upper()}</b>\n\n"
    
    builder = InlineKeyboardBuilder()
    
    for feat in features:
        status = "✅ Вкл" if feat.access else "❌ Выкл"
        text += f"<b>{feat.feature}</b>\n"
        text += f"   Статус: {status} | Лимит: {feat.limit_value or '—'}\n\n"
        
        # Кнопка вкл/выкл
        action = "off" if feat.access else "on"
        btn_icon = "❌" if feat.access else "✅"
        builder.button(
            text=f"{btn_icon} {feat.feature}",
            callback_data=f"admin:toggle:{tariff}:{feat.feature}:{action}"
        )
        # Кнопка изменить лимит
        builder.button(
            text="📝 Лимит",
            callback_data=f"admin:limit:{tariff}:{feat.feature}"
        )
    
    builder.button(text="← Назад в меню", callback_data="admin:menu")
    builder.adjust(2)  # По 2 кнопки в ряд (вкл/выкл + лимит)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("admin:toggle:"))
async def admin_toggle_feature(callback: types.CallbackQuery):
    """
    Переключает access (вкл/выкл) для функции.
    """
    parts = callback.data.split(":")
    tariff = parts[2]
    feature = parts[3]
    new_access = parts[4] == "on"
    
    async with async_session() as session:
        result = await session.execute(
            select(TariffFeature).where(
                TariffFeature.tariff == tariff,
                TariffFeature.feature == feature
            )
        )
        feat = result.scalar_one_or_none()
        
        if feat:
            feat.access = new_access
            await session.commit()
    
    status = "включена" if new_access else "выключена"
    await callback.answer(f"✅ {feature} {status} для {tariff}")
    
    # Обновляем экран
    await admin_show_tariff(callback)


@router.callback_query(F.data.startswith("admin:limit:"))
async def admin_edit_limit_start(callback: types.CallbackQuery, state: FSMContext):
    """
    Начинает диалог изменения лимита. Переводит в состояние ожидания числа.
    """
    parts = callback.data.split(":")
    tariff = parts[2]
    feature = parts[3]
    
    await state.set_state(AdminEditLimit.waiting_for_value)
    await state.update_data(tariff=tariff, feature=feature)
    
    await callback.message.answer(
        f"📝 <b>Изменение лимита</b>\n\n"
        f"Тариф: <b>{tariff.upper()}</b>\n"
        f"Функция: <b>{feature}</b>\n\n"
        f"Введи новое числовое значение:\n"
        f"• <code>0</code> — нет доступа / безлимит (зависит от логики)\n"
        f"• <code>15</code>, <code>5000</code> и т.д. — конкретный лимит\n\n"
        f"Для отмены напиши /start"
    )
    await callback.answer()


@router.message(AdminEditLimit.waiting_for_value)
async def admin_edit_limit_finish(message: types.Message, state: FSMContext):
    """
    Получает число от пользователя и сохраняет новый лимит.
    """
    data = await state.get_data()
    tariff = data["tariff"]
    feature = data["feature"]
    
    try:
        new_limit = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Нужно ввести целое число. Попробуй снова.")
        return
    
    async with async_session() as session:
        result = await session.execute(
            select(TariffFeature).where(
                TariffFeature.tariff == tariff,
                TariffFeature.feature == feature
            )
        )
        feat = result.scalar_one_or_none()
        
        if feat:
            feat.limit_value = new_limit
            await session.commit()
    
    await state.clear()
    await message.answer(
        f"✅ <b>Лимит обновлён!</b>\n\n"
        f"Тариф: {tariff.upper()}\n"
        f"Функция: {feature}\n"
        f"Новый лимит: <b>{new_limit}</b>\n\n"
        f"Проверь: /admin"
    )


@router.callback_query(F.data == "admin:menu")
async def admin_back_to_menu(callback: types.CallbackQuery):
    """Возвращает в главное меню админ-панели."""
    await _send_admin_menu(callback, callback.from_user.id)
    await callback.answer()


# ============ FSM: РЕГИСТРАЦИЯ (без изменений) ============

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


# ============ FSM: ВВОД КЛЮЧА BYOK (без изменений) ============

@router.message(ByokInput.waiting_for_key)
async def process_byok_key(message: types.Message, state: FSMContext):
    key = message.text.strip()

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


# ============ !-КОМАНДЫ СИСТЕМЫ (ЭТАП 7.1 — ТРЕКИ) ============

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
    """Сохраняет треки обратно в объект состояния"""
    user_state.tracks = tracks


@router.message(F.text.startswith("!"))
async def system_commands(message: types.Message):
    """
    Единый обработчик !-команд.
    Работает как маршрутизатор: определяет команду и вызывает нужную логику.
    """
    text = message.text.strip()
    parts = text.split(maxsplit=2)
    cmd = parts[0].upper()
    
    # Получаем или создаём user_state
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
        
        tracks.append({"name": name, "status": "active"})
        _save_tracks(user_state, tracks)
        
        async with async_session() as session:
            session.add(user_state)
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
            session.add(user_state)
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
            session.add(user_state)
            await session.commit()
        
        await message.answer(f"⏸ Трек «<b>{name}</b>» поставлен на паузу.")
        return
    
    # ==================== НЕИЗВЕСТНАЯ КОМАНДА ====================
    await message.answer(
        f"❓ Неизвестная команда: <code>{message.text[:30]}</code>\n\n"
        f"📋 <b>Доступные !-команды:</b>\n"
        f"<code>!ТРЕКИ</code> — список треков\n"
        f"<code>!ТРЕК ДОБАВИТЬ Название</code>\n"
        f"<code>!ТРЕК УДАЛИТЬ Название</code>\n"
        f"<code>!ТРЕК ПАУЗА Название</code>"
    )


# ============ УМНЫЙ ОБРАБОТЧИК (ИЗМЕНЕНО — счётчик токенов) ============

@router.message(F.text == "🔧 Админ-меню")
async def admin_menu_button(message: types.Message):
    """Обрабатывает нажатие reply-кнопки Админ-меню (только владелец)"""
    await _send_admin_menu(message, message.from_user.id)


# ============ АДМИН: ВЫБОР РАЗДЕЛА ============

@router.callback_query(F.data == "admin:section:features")
async def admin_section_features(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="🆓 Lite", callback_data="admin:tariff:lite")
    builder.button(text="⚡ Pro", callback_data="admin:tariff:pro")
    builder.button(text="💎 Business", callback_data="admin:tariff:business")
    builder.button(text="← Назад", callback_data="admin:menu")
    builder.adjust(3)
    
    await callback.message.edit_text(
        "⚙️ <b>Настройка фич тарифа</b>\n\nВыбери тариф:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data == "admin:section:roles")
async def admin_section_roles(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="🆓 Lite", callback_data="admin:roles:tariff:lite:page:0")
    builder.button(text="⚡ Pro", callback_data="admin:roles:tariff:pro:page:0")
    builder.button(text="💎 Business", callback_data="admin:roles:tariff:business:page:0")
    builder.button(text="← Назад", callback_data="admin:menu")
    builder.adjust(3)
    
    await callback.message.edit_text(
        "🎭 <b>Настройка ролей по тарифам</b>\n\n"
        "Здесь ты решаешь, какие роли доступны в каждом тарифе.\n\n"
        "Выбери тариф:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data == "admin:commands")
async def admin_commands_list(callback: types.CallbackQuery):
    text = (
        "📋 <b>Админ-команды</b>\n\n"
        "/admin — главное меню\n"
        "/upload_prompt — загрузить новый промпт\n"
        "/settariff [lite/pro/business] — сменить свой тариф\n"
        "/setkey — ввести BYOK-ключ\n\n"
        "⚠️ Все эти команды доступны только тебе (владельцу)."
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="← Назад", callback_data="admin:menu")
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


# ============ АДМИН: УПРАВЛЕНИЕ РОЛЯМИ ============

@router.callback_query(F.data.startswith("admin:roles:tariff:"))
async def admin_roles_list(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    tariff = parts[3]
    page = int(parts[5]) if len(parts) > 5 else 0
    
    async with async_session() as session:
        result = await session.execute(
            select(Role).where(Role.is_active == True).order_by(Role.id)
        )
        all_roles = result.scalars().all()
        
        access_result = await session.execute(
            select(RoleTariffAccess).where(RoleTariffAccess.tariff == tariff)
        )
        access_map = {a.role_id: a.access for a in access_result.scalars().all()}
    
    icon = "🆓" if tariff == "lite" else "⚡" if tariff == "pro" else "💎"
    per_page = 10
    total_pages = (len(all_roles) + per_page - 1) // per_page
    start = page * per_page
    end = start + per_page
    page_roles = all_roles[start:end]
    
    text = f"{icon} <b>Роли для тарифа {tariff.upper()}</b> (стр. {page+1}/{total_pages})\n\n"
    text += "Нажми на роль, чтобы переключить доступ:\n\n"
    
    builder = InlineKeyboardBuilder()
    
    for role in page_roles:
        access = access_map.get(role.id, False)
        status = "✅" if access else "❌"
        btn_text = f"{status} {role.name[:35]}"
        builder.button(
            text=btn_text,
            callback_data=f"admin:role:toggle:{tariff}:{role.id}"
        )
    
    builder.adjust(1)
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(("← Назад", f"admin:roles:tariff:{tariff}:page:{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(("Вперёд →", f"admin:roles:tariff:{tariff}:page:{page+1}"))
    nav_buttons.append(("← К тарифам", "admin:section:roles"))
    
    for text_btn, data in nav_buttons:
        builder.button(text=text_btn, callback_data=data)
    
    builder.adjust(2, 1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("admin:role:toggle:"))
async def admin_role_toggle(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    tariff = parts[3]
    role_id = int(parts[4])
    
    async with async_session() as session:
        result = await session.execute(
            select(RoleTariffAccess).where(
                RoleTariffAccess.role_id == role_id,
                RoleTariffAccess.tariff == tariff
            )
        )
        access = result.scalar_one_or_none()
        
        if access:
            access.access = not access.access
            new_status = access.access
        else:
            session.add(RoleTariffAccess(role_id=role_id, tariff=tariff, access=True))
            new_status = True
        
        await session.commit()
    
    status_text = "включена" if new_status else "выключена"
    await callback.answer(f"Роль {status_text} для {tariff}")
    
    # Обновляем список (редирект на страницу 0 для простоты)
    callback.data = f"admin:roles:tariff:{tariff}:page:0"
    await admin_roles_list(callback)


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
        
    selected_roles = await select_roles(message.from_user.id, message.text, max_roles=max_roles)
    
    system_prompt = await build_system_prompt(message.from_user.id, selected_roles)
    
    roles_names = ", ".join([r.name.split(":")[0] for r in selected_roles[:3]])
    try:
        await wait_msg.edit_text(f"⚡ Активированы роли: {roles_names}\n⏳ Думаю...")
    except Exception:
        pass

    # --- ОТПРАВЛЯЕМ В AI ---
    answer, success = await ask_llm(
        prompt=message.text,
        user_id=message.from_user.id,
        model=default_model,
        system_prompt=system_prompt
    )

       # --- Показываем ответ и обновляем счётчик токенов ---
    if success:
        # ← НОВОЕ: примерно считаем токены и сохраняем в БД
        try:
            tokens_used = count_tokens(message.text) + count_tokens(answer)
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
        roles_info = f"\n\n<i>🎭 Активные роли: {roles_names}</i>" if selected_roles else ""
        
        # ← НОВОЕ: разбиваем длинный ответ на части (лимит Telegram 4096)
        full_text = f"{source_icon} <b>Ответ AI:</b>\n\n{answer}{roles_info}"
        
        if len(full_text) > 4000:
            parts = [answer[i:i+4000] for i in range(0, len(answer), 4000)]
            for idx, part in enumerate(parts):
                prefix = f"{source_icon} <b>Ответ AI (часть {idx+1}/{len(parts)}):</b>\n\n"
                suffix = roles_info if idx == len(parts) - 1 else ""
                await message.answer(f"{prefix}{part}{suffix}")
        else:
            await message.answer(full_text)
    else:
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{answer}")
        

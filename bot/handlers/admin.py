# ============================================
# АДМИН-ПАНЕЛЬ И УПРАВЛЕНИЕ ПРОМПТОМ
# ============================================
# Здесь:
# • /admin — админ-панель с inline-кнопками
# • /settariff — смена тарифа
# • /upload_prompt — загрузка .md файла с FSM-защитой
# • Настройка tariff_features и RoleTariffAccess

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from bot.states import UploadPrompt, AdminEditLimit
from db.database import async_session
from db.models import User, Role, Rule, Command as CommandModel, TariffFeature, RoleTariffAccess
from config.settings import settings

router = Router()


# ============ /ADMIN ============

@router.message(Command(commands="admin"))
async def cmd_admin(message: types.Message):
    await _send_admin_menu(message, message.from_user.id)


async def _send_admin_menu(target, user_id: int):
    """Показывает главное меню админ-панели"""
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


# ============ /SETTARIFF ============

@router.message(Command(commands="settariff"))
async def cmd_settariff(message: types.Message):
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


# ============ /UPLOAD_PROMPT ============

@router.message(Command(commands="upload_prompt"))
async def cmd_upload_prompt(message: types.Message, state: FSMContext):
    if message.from_user.id != settings.owner_id:
        await message.answer("⛔ Эта команда только для владельца бота.")
        return

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
    current_state = await state.get_state()
    if current_state != UploadPrompt.waiting_for_file.state:
        return

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


@router.message(F.text, ~F.text.startswith('/'), UploadPrompt.waiting_for_file)
async def handle_text_upload(message: types.Message, state: FSMContext):
    if message.from_user.id != settings.owner_id:
        return

    if len(message.text) < 1000:
        await message.answer("❌ Слишком короткий текст для промпта. Минимум 1000 символов.")
        return

    wait_msg = await message.answer("🔍 Парсю текст...")
    await _process_prompt_text(message, message.text, wait_msg, state)


async def _process_prompt_text(message: types.Message, text: str, wait_msg: types.Message, state: FSMContext):
    from parsers.prompt_parser import parse_prompt_text

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
            result = await session.execute(select(CommandModel).where(CommandModel.name == cmd.name))
            existing = result.scalar_one_or_none()

            if existing:
                existing.description = cmd.description
                existing.cluster = cmd.cluster
                existing.tier_access = cmd.tier_access
                updated_cmds += 1
            else:
                session.add(CommandModel(
                    cluster=cmd.cluster,
                    name=cmd.name,
                    description=cmd.description,
                    tier_access=cmd.tier_access
                ))
                added_cmds += 1

        await session.commit()

        # Создаём дефолтные доступы для ролей
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


# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ РЕНДЕРИНГА ============

async def _render_tariff_features(target_message, tariff: str):
    """Рендерит список фич тарифа"""
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

        action = "off" if feat.access else "on"
        btn_icon = "❌" if feat.access else "✅"
        builder.button(
            text=f"{btn_icon} {feat.feature}",
            callback_data=f"admin:toggle:{tariff}:{feat.feature}:{action}"
        )
        builder.button(
            text="📝 Лимит",
            callback_data=f"admin:limit:{tariff}:{feat.feature}"
        )

    builder.button(text="← Назад в меню", callback_data="admin:menu")
    builder.adjust(2)

    try:
        await target_message.edit_text(text, reply_markup=builder.as_markup())
    except Exception as e:
        if "message is not modified" in str(e):
            pass
        else:
            raise


async def _render_roles_list(target_message, tariff: str, page: int = 0):
    """Рендерит список ролей для тарифа"""
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

    try:
        await target_message.edit_text(text, reply_markup=builder.as_markup())
    except Exception as e:
        if "message is not modified" in str(e):
            pass
        else:
            raise


# ============ CALLBACK ОБРАБОТЧИКИ АДМИНКИ ============

@router.callback_query(F.data.startswith("admin:tariff:"))
async def admin_show_tariff(callback: types.CallbackQuery):
    """Показывает фичи конкретного тарифа"""
    tariff = callback.data.split(":")[2]
    await _render_tariff_features(callback.message, tariff)
    await callback.answer()


@router.callback_query(F.data.startswith("admin:toggle:"))
async def admin_toggle_feature(callback: types.CallbackQuery):
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
    await _render_tariff_features(callback.message, tariff)


@router.callback_query(F.data.startswith("admin:limit:"))
async def admin_edit_limit_start(callback: types.CallbackQuery, state: FSMContext):
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
    await _send_admin_menu(callback, callback.from_user.id)
    await callback.answer()


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


@router.callback_query(F.data.startswith("admin:roles:tariff:"))
async def admin_roles_list(callback: types.CallbackQuery):
    """Показывает список ролей для тарифа (с пагинацией)"""
    parts = callback.data.split(":")
    tariff = parts[3]
    page = int(parts[5]) if len(parts) > 5 else 0
    await _render_roles_list(callback.message, tariff, page)
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

    # Обновляем список
    await _render_roles_list(callback.message, tariff, 0)

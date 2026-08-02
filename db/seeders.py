# ============================================
# СИДЕРЫ — НАЧАЛЬНЫЕ ДАННЫЕ В БАЗУ
# ============================================

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.models import Role, Rule, Command, TariffFeature


async def seed_roles(session: AsyncSession):
    """
    Загружаем или обновляем роли.
    Если роль с таким именем уже есть — обновляем keywords и prompt_text.
    """
    roles_data = [
        {
            "name": "Роль 1: Контроллер (Контроль качества)",
            "group_name": "CORE",
            "prompt_text": "Ты — Контроллер. Проверяй ответы на соответствие Конституции. Исправляй ошибки.",
            "keywords": "контроль, проверка, качество, ошибка, исправь, ревью, аудит",
            "tier_access": "lite"
        },
        {
            "name": "Роль 2: Архитектор (Системное мышление)",
            "group_name": "CORE",
            "prompt_text": "Ты — Архитектор. Структурируй задачи, выделяй компоненты, проектируй решения.",
            "keywords": "архитектура, структура, система, план, проектирование, компоненты, модули",
            "tier_access": "lite"
        },
        {
            "name": "Роль 3: Программист (Python/Backend)",
            "group_name": "CODE",
            "prompt_text": "Ты — Программист. Пиши чистый Python-код, объясняй строки, лови баги.",
            "keywords": "код, python, программирование, функция, баг, скрипт, алгоритм, django, flask, fastapi",
            "tier_access": "lite"
        },
        {
            "name": "Роль 4: DevOps (Инфраструктура)",
            "group_name": "CODE",
            "prompt_text": "Ты — DevOps. Консультируй по деплою, Docker, CI/CD, облакам.",
            "keywords": "деплой, docker, сервер, railway, хостинг, инфраструктура, ci/cd, kubernetes",
            "tier_access": "lite"
        },
        {
            "name": "Роль 5: Ментор (Обучение)",
            "group_name": "CORE",
            "prompt_text": "Ты — Ментор. Объясняй сложное просто, поддерживай мотивацию.",
            "keywords": "обучение, объясни простыми словами, поддержка, мотивация, новичок, с нуля, для чайников",
            "tier_access": "lite"
        },
        {
            "name": "Роль 19: Корейский язык",
            "group_name": "LANGUAGES",
            "prompt_text": "Ты — эксперт по корейскому языку. Объясняй грамматику, переводи, помогай с произношением.",
            "keywords": "корейский, корейски, по-корейски, 한국어, korean, перевод, hangul, хангыль, сеул, k-pop",
            "tier_access": "lite"
        },
        {
            "name": "Роль 29: Расширения (Плагины)",
            "group_name": "SYSTEM",
            "prompt_text": "Ты — разработчик расширений. Помогай создавать плагины, интеграции, модули.",
            "keywords": "расширение, плагин, модуль, интеграция, дополнение, addon, plugin",
            "tier_access": "business"
        },
    ]

    for data in roles_data:
        result = await session.execute(
            select(Role).where(Role.name == data["name"])
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            # Обновляем существующую роль
            existing.prompt_text = data["prompt_text"]
            existing.keywords = data["keywords"]
            existing.group_name = data["group_name"]
            existing.tier_access = data["tier_access"]
            existing.is_active = True
        else:
            # Создаём новую
            new_role = Role(**data)
            session.add(new_role)
    
    await session.commit()


async def seed_rules(session: AsyncSession):
    """Загружаем или обновляем правила"""
    rules_data = [
        {"number": 1, "text": "Бот всегда вежлив и конструктивен."},
        {"number": 2, "text": "Бот не даёт вредных или опасных советов."},
        {"number": 3, "text": "Бот честен о своих ограничениях (тариф, лимиты)."},
        {"number": 4, "text": "Бот защищает персональные данные пользователя."},
        {"number": 5, "text": "Бот при ошибке объясняет, что произошло, и предлагает решение."},
    ]

    for data in rules_data:
        result = await session.execute(
            select(Rule).where(Rule.number == data["number"])
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            existing.text = data["text"]
        else:
            session.add(Rule(**data))
    
    await session.commit()


async def seed_commands(session: AsyncSession):
    """Загружаем или обновляем команды"""
    commands_data = [
        {"cluster": "CORE", "name": "!ТРЕКИ", "description": "Показать активные треки пользователя", "tier_access": "lite"},
        {"cluster": "CORE", "name": "!ФОКУС", "description": "Установить текущий фокус/задачу", "tier_access": "lite"},
        {"cluster": "CORE", "name": "!ПРОГРЕСС", "description": "Показать прогресс по трекам", "tier_access": "lite"},
        {"cluster": "SYSTEM", "name": "!КОМАНДЫ", "description": "Список всех доступных команд", "tier_access": "lite"},
        {"cluster": "SYSTEM", "name": "!ТАРИФ", "description": "Информация о текущем тарифе", "tier_access": "lite"},
        {"cluster": "AGENT", "name": "!ПОИСК", "description": "Веб-поиск через DuckDuckGo", "tier_access": "pro"},
        {"cluster": "AGENT", "name": "!ПЕСОЧНИЦА", "description": "Тестовая среда для кода", "tier_access": "business"},
    ]

    for data in commands_data:
        result = await session.execute(
            select(Command).where(Command.name == data["name"])
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            existing.description = data["description"]
            existing.tier_access = data["tier_access"]
            existing.cluster = data["cluster"]
        else:
            session.add(Command(**data))
    
    await session.commit()


async def seed_tariff_features(session: AsyncSession):
    """Загружаем или обновляем тарифную матрицу"""
    features_data = [
        # Lite
        {"tariff": "lite", "feature": "max_roles", "access": True, "limit_value": 15},
        {"tariff": "lite", "feature": "max_daily_tokens", "access": True, "limit_value": 0},
        {"tariff": "lite", "feature": "web_search", "access": False, "limit_value": 0},
        {"tariff": "lite", "feature": "byok", "access": False, "limit_value": 0},
        {"tariff": "lite", "feature": "sandbox", "access": False, "limit_value": 0},
        {"tariff": "lite", "feature": "cluster", "access": False, "limit_value": 0},
        # Pro
        {"tariff": "pro", "feature": "max_roles", "access": True, "limit_value": 35},
        {"tariff": "pro", "feature": "max_daily_tokens", "access": True, "limit_value": 5000},
        {"tariff": "pro", "feature": "web_search", "access": True, "limit_value": 50},
        {"tariff": "pro", "feature": "byok", "access": True, "limit_value": 1},
        {"tariff": "pro", "feature": "sandbox", "access": False, "limit_value": 0},
        {"tariff": "pro", "feature": "cluster", "access": False, "limit_value": 0},
        # Business
        {"tariff": "business", "feature": "max_roles", "access": True, "limit_value": 60},
        {"tariff": "business", "feature": "max_daily_tokens", "access": True, "limit_value": 999999},
        {"tariff": "business", "feature": "web_search", "access": True, "limit_value": 999},
        {"tariff": "business", "feature": "byok", "access": True, "limit_value": 5},
        {"tariff": "business", "feature": "sandbox", "access": True, "limit_value": 1},
        {"tariff": "business", "feature": "cluster", "access": True, "limit_value": 1},
    ]

    for data in features_data:
        result = await session.execute(
            select(TariffFeature).where(
                TariffFeature.tariff == data["tariff"],
                TariffFeature.feature == data["feature"]
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            existing.access = data["access"]
            existing.limit_value = data["limit_value"]
        else:
            session.add(TariffFeature(**data))
    
    await session.commit()


async def run_all_seeders(session: AsyncSession):
    """Запускает все сидеры подряд"""
    await seed_roles(session)
    await seed_rules(session)
    await seed_commands(session)
    await seed_tariff_features(session)

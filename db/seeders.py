# ============================================
# СИДЕРЫ — НАЧАЛЬНЫЕ ДАННЫЕ В БАЗУ
# ============================================
# При первом запуске бота эти данные автоматически загрузятся в таблицы.

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.models import Role, Rule, Command, TariffFeature


async def seed_roles(session: AsyncSession):
    """
    Загружаем 7 базовых ролей (ядро системы).
    Остальные 53 роли загрузим позже через админ-панель.
    """
    # Проверяем, есть ли уже роли в базе
    result = await session.execute(select(Role))
    if result.scalars().first():
        return  # Роли уже есть, не дублируем
    
    roles = [
        Role(
            name="Роль 1: Контроллер (Контроль качества)",
            group_name="CORE",
            prompt_text="Ты — Контроллер. Проверяй ответы других ролей на соответствие Конституции. Исправляй ошибки, указывай на нарушения.",
            keywords="контроль, проверка, качество, ошибка, исправь",
            is_active=True,
            tier_access="lite"
        ),
        Role(
            name="Роль 2: Архитектор (Системное мышление)",
            group_name="CORE",
            prompt_text="Ты — Архитектор. Структурируй сложные задачи, выделяй компоненты, предлагай архитектуру решения.",
            keywords="архитектура, структура, система, план, проектирование",
            is_active=True,
            tier_access="lite"
        ),
        Role(
            name="Роль 3: Программист (Python/Backend)",
            group_name="CODE",
            prompt_text="Ты — Программист. Пиши чистый Python-код, объясняй каждую строку, предупреждай об ошибках.",
            keywords="код, python, программирование, функция, баг, скрипт",
            is_active=True,
            tier_access="lite"
        ),
        Role(
            name="Роль 4: DevOps (Инфраструктура)",
            group_name="CODE",
            prompt_text="Ты — DevOps. Консультируй по деплою, Docker, CI/CD, облачным сервисам.",
            keywords="деплой, docker, сервер, railway, хостинг, инфраструктура",
            is_active=True,
            tier_access="lite"
        ),
        Role(
            name="Роль 5: Ментор (Обучение)",
            group_name="CORE",
            prompt_text="Ты — Ментор. Объясняй сложное простыми словами, поддерживай мотивацию, следи за прогрессом.",
            keywords="обучение, объясни, как, почему, помощь, новичок",
            is_active=True,
            tier_access="lite"
        ),
        Role(
            name="Роль 19: Корейский язык",
            group_name="LANGUAGES",
            prompt_text="Ты — эксперт по корейскому языку. Объясняй грамматику, переводи, помогай с произношением.",
            keywords="корейский, 한국어, korean, перевод, hangul",
            is_active=True,
            tier_access="lite"
        ),
        Role(
            name="Роль 29: Расширения (Плагины)",
            group_name="SYSTEM",
            prompt_text="Ты — разработчик расширений. Помогай создавать плагины, интеграции, дополнительные модули.",
            keywords="расширение, плагин, модуль, интеграция, дополнение",
            is_active=True,
            tier_access="business"  # Эта роль только в Business
        ),
    ]
    
    session.add_all(roles)
    await session.commit()


async def seed_rules(session: AsyncSession):
    """Загружаем 5 базовых правил (Конституция)"""
    result = await session.execute(select(Rule))
    if result.scalars().first():
        return
    
    rules = [
        Rule(number=1, text="Бот всегда вежлив и конструктивен."),
        Rule(number=2, text="Бот не даёт вредных или опасных советов."),
        Rule(number=3, text="Бот честен о своих ограничениях (тариф, лимиты)."),
        Rule(number=4, text="Бот защищает персональные данные пользователя."),
        Rule(number=5, text="Бот при ошибке объясняет, что произошло, и предлагает решение."),
    ]
    
    session.add_all(rules)
    await session.commit()


async def seed_commands(session: AsyncSession):
    """Загружаем базовые команды системы"""
    result = await session.execute(select(Command))
    if result.scalars().first():
        return
    
    commands = [
        Command(cluster="CORE", name="!ТРЕКИ", description="Показать активные треки пользователя", tier_access="lite"),
        Command(cluster="CORE", name="!ФОКУС", description="Установить текущий фокус/задачу", tier_access="lite"),
        Command(cluster="CORE", name="!ПРОГРЕСС", description="Показать прогресс по трекам", tier_access="lite"),
        Command(cluster="SYSTEM", name="!КОМАНДЫ", description="Список всех доступных команд", tier_access="lite"),
        Command(cluster="SYSTEM", name="!ТАРИФ", description="Информация о текущем тарифе", tier_access="lite"),
        Command(cluster="AGENT", name="!ПОИСК", description="Веб-поиск через DuckDuckGo", tier_access="pro"),
        Command(cluster="AGENT", name="!ПЕСОЧНИЦА", description="Тестовая среда для кода", tier_access="business"),
    ]
    
    session.add_all(commands)
    await session.commit()


async def seed_tariff_features(session: AsyncSession):
    """Загружаем тарифную матрицу (что доступно в каждом тарифе)"""
    result = await session.execute(select(TariffFeature))
    if result.scalars().first():
        return
    
    features = [
        # Lite
        TariffFeature(tariff="lite", feature="max_roles", access=True, limit_value=15),
        TariffFeature(tariff="lite", feature="max_daily_tokens", access=True, limit_value=0),
        TariffFeature(tariff="lite", feature="web_search", access=False, limit_value=0),
        TariffFeature(tariff="lite", feature="byok", access=False, limit_value=0),
        TariffFeature(tariff="lite", feature="sandbox", access=False, limit_value=0),
        TariffFeature(tariff="lite", feature="cluster", access=False, limit_value=0),
        
        # Pro
        TariffFeature(tariff="pro", feature="max_roles", access=True, limit_value=35),
        TariffFeature(tariff="pro", feature="max_daily_tokens", access=True, limit_value=5000),
        TariffFeature(tariff="pro", feature="web_search", access=True, limit_value=50),
        TariffFeature(tariff="pro", feature="byok", access=True, limit_value=1),
        TariffFeature(tariff="pro", feature="sandbox", access=False, limit_value=0),
        TariffFeature(tariff="pro", feature="cluster", access=False, limit_value=0),
        
        # Business
        TariffFeature(tariff="business", feature="max_roles", access=True, limit_value=60),
        TariffFeature(tariff="business", feature="max_daily_tokens", access=True, limit_value=999999),
        TariffFeature(tariff="business", feature="web_search", access=True, limit_value=999),
        TariffFeature(tariff="business", feature="byok", access=True, limit_value=5),
        TariffFeature(tariff="business", feature="sandbox", access=True, limit_value=1),
        TariffFeature(tariff="business", feature="cluster", access=True, limit_value=1),
    ]
    
    session.add_all(features)
    await session.commit()


async def run_all_seeders(session: AsyncSession):
    """Запускает все сидеры подряд"""
    await seed_roles(session)
    await seed_rules(session)
    await seed_commands(session)
    await seed_tariff_features(session)

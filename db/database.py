# ============================================
# ПОДКЛЮЧЕНИЕ К БАЗЕ ДАННЫХ
# ============================================

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from config.settings import settings

# Если Railway дал обычный postgresql://, меняем на asyncpg-версию
# (asyncpg — это драйвер для асинхронной работы с PostgreSQL)
DATABASE_URL = settings.database_url
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Создаём "движок" — это соединение с базой данных
engine = create_async_engine(DATABASE_URL, echo=False)

# Создаём фабрику сессий (сессия = одна операция с базой)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Базовый класс для всех таблиц (моделей)
Base = declarative_base()


async def init_db():
    """
    Создаёт все таблицы в базе данных при первом запуске.
    Если таблицы уже есть — ничего не делает (не удаляет данные).
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """
    Открывает сессию с базой данных.
    Используется в обработчиках бота.
    """
    async with async_session() as session:
        return session

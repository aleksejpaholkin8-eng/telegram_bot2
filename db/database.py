from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from config.settings import settings

# Если Railway дал обычный postgresql://, меняем на asyncpg-версию
DATABASE_URL = settings.database_url
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Создаём "движок" — соединение с базой данных
engine = create_async_engine(DATABASE_URL, echo=False)

# Создаём фабрику сессий
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Базовый класс для всех таблиц
Base = declarative_base()


async def init_db():
    """
    Создаёт все таблицы в базе данных при первом запуске.
    Если таблицы уже есть — ничего не делает.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ← ИСПРАВЛЕНИЕ: get_session теперь работает как async context manager
async def get_session():
    """
    Асинхронный контекстный менеджер для сессии БД.
    Использование:
        async with get_session() as session:
            result = await session.execute(...)
    """
    async with async_session() as session:
        yield session

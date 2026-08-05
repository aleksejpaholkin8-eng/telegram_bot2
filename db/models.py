from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, BigInteger, JSON
from sqlalchemy.sql import func

from db.database import Base


class User(Base):
    """Таблица пользователей Telegram"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    tariff = Column(String(20), default="lite")  # lite / pro / business
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Role(Base):
    """Таблица ролей (60 ролей из Промпта 1)"""
    __tablename__ = "roles"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)          # Название роли
    group_name = Column(String(100), nullable=True)     # Группа (например, "Языки", "Код")
    prompt_text = Column(Text, nullable=False)          # Текст промпта роли
    keywords = Column(Text, nullable=True)              # Ключевые слова для роутинга (через запятую)
    is_active = Column(Boolean, default=True)           # Включена ли роль
    tier_access = Column(String(20), default="lite")    # Минимальный тариф: lite/pro/business


class Rule(Base):
    """Таблица правил (Конституция)"""
    __tablename__ = "rules"
    
    id = Column(Integer, primary_key=True, index=True)
    number = Column(Integer, nullable=False)            # Номер статьи
    text = Column(Text, nullable=False)                 # Текст правила
    is_active = Column(Boolean, default=True)


class Command(Base):
    """Таблица команд системы (!ТРЕКИ, !ФОКУС...)"""
    __tablename__ = "commands"
    
    id = Column(Integer, primary_key=True, index=True)
    cluster = Column(String(50), nullable=False)        # Кластер (CORE, SYSTEM, AGENT...)
    name = Column(String(100), nullable=False)          # Имя команды (!ТРЕКИ)
    description = Column(Text, nullable=True)           # Описание
    handler_name = Column(String(100), nullable=True)   # Имя обработчика в коде
    tier_access = Column(String(20), default="lite")    # Доступность по тарифу


class UserState(Base):
    """Состояние пользователя (треки, паспорт, счётчики)"""
    __tablename__ = "user_states"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    license_mode = Column(String(20), default="lite")   # lite / pro / business
    api_source = Column(String(20), default="owner")    # owner / byok
    json_passport = Column(JSON, default=dict)          # JSON-паспорт пользователя
    tracks = Column(JSON, default=list)                 # Список треков
    counters = Column(JSON, default=dict)               # Счётчики (токены, запросы)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserApiKey(Base):
    """API-ключи пользователей (BYOK)"""
    __tablename__ = "user_api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    provider = Column(String(50), nullable=False)       # groq / deepseek / openai...
    key_encrypted = Column(Text, nullable=False)        # Зашифрованный ключ
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TariffFeature(Base):
    """Тарифная матрица: что доступно в каждом тарифе"""
    __tablename__ = "tariff_features"
    
    id = Column(Integer, primary_key=True, index=True)
    tariff = Column(String(20), nullable=False)         # lite / pro / business
    feature = Column(String(100), nullable=False)       # Название функции
    access = Column(Boolean, default=False)             # Доступна ли функция
    limit_value = Column(Integer, nullable=True)        # Лимит (например, 5000 токенов)

class RoleTariffAccess(Base):
    """Какие роли доступны в каком тарифе (ручное управление админом)"""
    __tablename__ = "role_tariff_access"
    
    id = Column(Integer, primary_key=True, index=True)
    role_id = Column(Integer, nullable=False, index=True)
    tariff = Column(String(20), nullable=False, index=True)
    access = Column(Boolean, default=False)

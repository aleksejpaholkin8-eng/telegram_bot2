# ============================================
# СОСТОЯНИЯ FSM (Finite State Machine)
# ============================================
# FSM — это когда бот помнит, на каком шаге диалога находится пользователь.
# Например: "жду имя" → "жду цель" → "готово"

from aiogram.fsm.state import State, StatesGroup


class UserRegistration(StatesGroup):
    """Диалог регистрации нового пользователя"""
    waiting_for_name = State()      # Шаг 1: ждём имя
    waiting_for_goal = State()      # Шаг 2: ждём цель
    waiting_for_confirm = State()   # Шаг 3: ждём подтверждения


class ByokInput(StatesGroup):
    """Диалог ввода своего API-ключа (BYOK)"""
    waiting_for_key = State()


# ============ НОВОЕ: Шаг 5.4 ============
class UploadPrompt(StatesGroup):
    """
    Диалог загрузки промпта.
    Раньше бот ловил ЛЮБОЕ длинное сообщение как промпт — это баг.
    Теперь он ждёт промпт ТОЛЬКО после команды /upload_prompt.
    """
    waiting_for_file = State()


class AdminEditLimit(StatesGroup):
    """
    Диалог изменения лимита в админ-панели.
    Бот спрашивает число → пользователь вводит → бот сохраняет.
    """
    waiting_for_value = State()

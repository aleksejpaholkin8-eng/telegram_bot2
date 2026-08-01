# ============================================
# СОСТОЯНИЯ FSM (Finite State Machine)
# ============================================

from aiogram.fsm.state import State, StatesGroup


class UserRegistration(StatesGroup):
    """
    Диалог регистрации пользователя.
    """
    waiting_for_name = State()      # Шаг 1: ждём имя
    waiting_for_goal = State()      # Шаг 2: ждём цель
    waiting_for_confirm = State()   # Шаг 3: ждём "да" или "нет"


class ByokSetup(StatesGroup):
    """
    Диалог добавления своего API-ключа (BYOK).
    """
    waiting_for_provider = State()  # Шаг 1: выбор провайдера
    waiting_for_key = State()       # Шаг 2: ввод ключа

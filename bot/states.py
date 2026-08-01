# ============================================
# СОСТОЯНИЯ FSM (Finite State Machine)
# ============================================
# Здесь описаны шаги диалога с ботом.
# Каждое состояние = один шаг.

from aiogram.fsm.state import State, StatesGroup


class UserRegistration(StatesGroup):
    """
    Диалог регистрации пользователя.
    Бот по очереди проходит 3 шага:
    1. Спрашивает имя
    2. Спрашивает цель
    3. Просит подтвердить данные
    """
    waiting_for_name = State()      # Шаг 1: ждём имя
    waiting_for_goal = State()      # Шаг 2: ждём цель
    waiting_for_confirm = State()   # Шаг 3: ждём "да" или "нет"

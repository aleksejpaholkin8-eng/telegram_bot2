# ============================================
# СОСТОЯНИЯ FSM
# ============================================

from aiogram.fsm.state import State, StatesGroup


class UserRegistration(StatesGroup):
    """Диалог регистрации"""
    waiting_for_name = State()
    waiting_for_goal = State()
    waiting_for_confirm = State()


class ByokInput(StatesGroup):
    """Ввод своего API-ключа"""
    waiting_for_key = State()

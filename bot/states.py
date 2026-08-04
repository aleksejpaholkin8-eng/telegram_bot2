from aiogram.fsm.state import State, StatesGroup

class UserRegistration(StatesGroup):
    """Диалог регистрации"""
    waiting_for_name = State()
    waiting_for_goal = State()
    waiting_for_confirm = State()

class ByokInput(StatesGroup):
    """Ввод своего API-ключа"""
    waiting_for_key = State()

class UploadPrompt(StatesGroup):
    """Диалог загрузки промпта"""
    waiting_for_file = State()

class AdminEditLimit(StatesGroup):
    """Изменение лимита в админ-панели"""
    waiting_for_value = State()

class TrackMenu(StatesGroup):
    """Диалог управления треками через кнопки"""
    waiting_for_name = State()
    action = State()

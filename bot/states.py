from aiogram.fsm.state import State, StatesGroup


class UserRegistration(StatesGroup):
    waiting_for_name = State()
    waiting_for_goal = State()
    waiting_for_confirm = State()


class ByokInput(StatesGroup):
    waiting_for_key = State()


class UploadPrompt(StatesGroup):
    waiting_for_file = State()


class AdminEditLimit(StatesGroup):
    waiting_for_value = State()


class TrackMenu(StatesGroup):
    waiting_for_name = State()
    action = State()


class FocusInput(StatesGroup):
    waiting_for_topic = State()

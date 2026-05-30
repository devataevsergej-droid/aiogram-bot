from aiogram.fsm.state import State, StatesGroup


class WorkshopRegistration(StatesGroup):
    workshop = State()
    name = State()
    phone = State()
    
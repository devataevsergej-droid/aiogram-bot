from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu(user_role: str = None) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="📢 Разместить вакансию"), KeyboardButton(text="📝 Заполнить анкету")],
        [KeyboardButton(text="👥 Пригласить друга"), KeyboardButton(text="🔍 Смотреть вакансии")],
        [KeyboardButton(text="👤 Личный кабинет"), KeyboardButton(text="📺 Наш канал")],
    ]
    
    if user_role:
        toggle_text = "🔄 Переключиться на соискателя" if user_role == "employer" else "🔄 Переключиться на работодателя"
        keyboard.append([KeyboardButton(text=toggle_text)])
    
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие",
    )
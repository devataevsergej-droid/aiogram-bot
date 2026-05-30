from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def workshop_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора мастер-класса"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🕯 Свечи", callback_data="workshop:candles")],
            [InlineKeyboardButton(text="🧼 Мыло", callback_data="workshop:soap")],
            [InlineKeyboardButton(text="🪨 Гипс", callback_data="workshop:gypsum")],
            [InlineKeyboardButton(text="✨ Эпоксидная смола", callback_data="workshop:epoxy")],
            [InlineKeyboardButton(text="🤔 Пока не решил", callback_data="workshop:undecided")],
        ]
    )

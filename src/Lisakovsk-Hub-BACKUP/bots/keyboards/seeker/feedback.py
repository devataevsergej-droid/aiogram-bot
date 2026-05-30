from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def seeker_feedback_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для личного кабинета соискателя"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Я нашёл работу через бота", callback_data="found_work")],
            [InlineKeyboardButton(text="⭐ Купить VIP — 300 ₸", callback_data="manual:vip_seeker")],
        ]
    )


def vacancies_keyboard(vacancy_id: int) -> InlineKeyboardMarkup:
    """Клавиатура под вакансией при просмотре"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📩 Откликнуться", callback_data=f"vacancy_like:{vacancy_id}")],
            [
                InlineKeyboardButton(text="🙈 Скрыть", callback_data=f"vacancy_dislike:{vacancy_id}"),
                InlineKeyboardButton(text="⚠️ Пожаловаться", callback_data=f"vacancy_complain:{vacancy_id}"),
            ],
        ]
    )

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from job_lisakovsk_bot.constants import (
    FEATURE_PIN_VACANCY,
    FEATURE_UNLIMITED_VACANCIES,
    FEATURE_URGENT_BROADCAST,
    FEATURE_VIP_SEEKER,
    NOT_IMPORTANT,
    SCHEDULES,
    SPHERES,
)


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Ищу работу"), KeyboardButton(text="Ищу сотрудника")],
            [KeyboardButton(text="Смотреть вакансии"), KeyboardButton(text="Пригласить друга")],
            [KeyboardButton(text="Личный кабинет"), KeyboardButton(text="Наши проекты")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите режим",
    )


def options_keyboard(values: tuple[str, ...], prefix: str, include_not_important: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for value in values:
        builder.button(text=value, callback_data=f"{prefix}:{value}")
    if include_not_important:
        builder.button(text=NOT_IMPORTANT, callback_data=f"{prefix}:{NOT_IMPORTANT}")
    builder.adjust(2)
    return builder.as_markup()


def spheres_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return options_keyboard(SPHERES, prefix)


def schedules_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return options_keyboard(SCHEDULES, prefix)


def vacancies_keyboard(vacancy_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Откликнуться", callback_data=f"vacancy_like:{vacancy_id}")],
            [
                InlineKeyboardButton(text="Скрыть", callback_data=f"vacancy_dislike:{vacancy_id}"),
                InlineKeyboardButton(text="Пожаловаться", callback_data=f"vacancy_complain:{vacancy_id}"),
            ],
        ]
    )


def moderation_keyboard(vacancy_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"moderate_approve:{vacancy_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"moderate_reject:{vacancy_id}"),
            ],
        ]
    )


def vacancy_paid_features_keyboard(vacancy_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📌 Закрепить на 3 дня — 30 Stars", callback_data=f"buy:{FEATURE_PIN_VACANCY}:{vacancy_id}")],
            [InlineKeyboardButton(text="🚀 Срочная рассылка всем — 20 Stars", callback_data=f"buy:{FEATURE_URGENT_BROADCAST}:{vacancy_id}")],
        ]
    )


def buy_unlimited_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Купить безлимит — 50 Stars/месяц", callback_data=f"buy:{FEATURE_UNLIMITED_VACANCIES}")],
            [InlineKeyboardButton(text="Оплатить вручную на Билайн", callback_data=f"manual:{FEATURE_UNLIMITED_VACANCIES}")],
        ]
    )


def seeker_vip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ VIP соискателя — 30 Stars/месяц", callback_data=f"buy:{FEATURE_VIP_SEEKER}")],
            [InlineKeyboardButton(text="Оплатить вручную на Билайн", callback_data=f"manual:{FEATURE_VIP_SEEKER}")],
        ]
    )


def manual_payment_keyboard(payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Я оплатил", callback_data=f"manual_paid:{payment_id}")]]
    )


def admin_manual_payment_keyboard(payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"manual_confirm:{payment_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"manual_reject:{payment_id}"),
            ]
        ]
    )


def feedback_keyboard(latest_vacancy_id: int | None = None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="✅ Я нашёл работу через бота", callback_data="found_work")]]
    if latest_vacancy_id is not None:
        rows.append([InlineKeyboardButton(text="✅ Я закрыл вакансию через бота", callback_data=f"close_vacancy:{latest_vacancy_id}")])
    rows.append([InlineKeyboardButton(text="⭐ Купить VIP", callback_data=f"buy:{FEATURE_VIP_SEEKER}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def weekly_stats_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Подать анкету", url=f"https://t.me/{bot_username}?start=resume"),
                InlineKeyboardButton(text="📢 Разместить вакансию", url=f"https://t.me/{bot_username}?start=vacancy"),
            ],
            [InlineKeyboardButton(text="📤 Поделиться", switch_inline_query="Работа Лисаковск")],
        ]
    )

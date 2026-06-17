from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

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


def main_menu(
    user_role: str = None,
    is_admin: bool = False
) -> ReplyKeyboardMarkup:

    keyboard = []

    # Кнопка админа
    if is_admin:

        keyboard.append([
            KeyboardButton(text="📊 Админ-статистика")
        ])

    # Соискатель
    if user_role == "seeker":

        keyboard.extend([

            [
                KeyboardButton(text="📺 Лента вакансий"),
                KeyboardButton(text="📝 Заполнить анкету")
            ],

            [
                KeyboardButton(text="👤 Личный кабинет")
            ],

            [
                KeyboardButton(text="👥 Пригласить друга")
            ],

        ])

    # Работодатель
    elif user_role == "employer":

        keyboard.extend([

            [
                KeyboardButton(text="📢 Разместить вакансию")
            ],

            [
                KeyboardButton(text="👤 Личный кабинет")
            ],

            [
                KeyboardButton(text="📣 Поделиться проектом")
            ],

        ])

    # Новый пользователь
    else:

        keyboard.extend([

            [
                KeyboardButton(text="📢 Разместить вакансию")
            ],

            [
                KeyboardButton(text="📝 Заполнить анкету")
            ],

            [
                KeyboardButton(text="📺 Лента вакансий")
            ],

        ])

    # Переключение роли
    if user_role:

        toggle_text = (
            "🔄 Переключиться на соискателя"
            if user_role == "employer"
            else "🔄 Переключиться на работодателя"
        )

        keyboard.append([
            KeyboardButton(text=toggle_text)
        ])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие",
    )


def options_keyboard(
    values: tuple[str, ...],
    prefix: str,
    include_not_important: bool = False
) -> InlineKeyboardMarkup:

    builder = InlineKeyboardBuilder()

    for value in values:
        builder.button(
            text=value,
            callback_data=f"{prefix}:{value}"
        )

    if include_not_important:
        builder.button(
            text=NOT_IMPORTANT,
            callback_data=f"{prefix}:{NOT_IMPORTANT}"
        )

    builder.adjust(2)

    return builder.as_markup()


def spheres_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return options_keyboard(SPHERES, prefix)


def schedules_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return options_keyboard(SCHEDULES, prefix)


def vacancies_keyboard(vacancy_id: int) -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="📩 Откликнуться",
                    callback_data=f"vacancy_like:{vacancy_id}"
                ),
            ],

            [
                InlineKeyboardButton(
                    text="🙈 Скрыть",
                    callback_data=f"vacancy_dislike:{vacancy_id}"
                ),
            ],

            [
                InlineKeyboardButton(
                    text="⚠️ Пожаловаться",
                    callback_data=f"vacancy_complain:{vacancy_id}"
                ),
            ],
        ]
    )


def vacancy_responded_keyboard(
    vacancy_id: int
) -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="✅ Вы откликнулись",
                    callback_data=f"vacancy_already:{vacancy_id}"
                ),
            ],

            [
                InlineKeyboardButton(
                    text="🙈 Скрыть",
                    callback_data=f"vacancy_dislike:{vacancy_id}"
                ),
            ],

            [
                InlineKeyboardButton(
                    text="⚠️ Пожаловаться",
                    callback_data=f"vacancy_complain:{vacancy_id}"
                ),
            ],
        ]
    )

def moderation_keyboard(vacancy_id: int) -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Одобрить",
                    callback_data=f"moderate_approve:{vacancy_id}"
                ),

                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"moderate_reject:{vacancy_id}"
                ),
            ],
        ]
    )


def vacancy_paid_features_keyboard(
    vacancy_id: int,
    post_url: str
) -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="👀 Посмотреть вакансию",
                    url=post_url
                )
            ],

            [
                InlineKeyboardButton(
                    text="📌 Закрепить в канале — 300 ₸",
                    callback_data=f"manual:{FEATURE_PIN_VACANCY}:{vacancy_id}"
                )
            ],

            [
                InlineKeyboardButton(
                    text="🚀 Срочная рассылка — 200 ₸",
                    callback_data=f"manual:{FEATURE_URGENT_BROADCAST}:{vacancy_id}"
                )
            ],
        ]
    )


def buy_unlimited_keyboard() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Купить безлимит — 500 ₸",
                    callback_data=f"manual:{FEATURE_UNLIMITED_VACANCIES}"
                )
            ]
        ]
    )


def seeker_vip_keyboard() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ VIP соискателя — 300 ₸",
                    callback_data=f"manual:{FEATURE_VIP_SEEKER}"
                )
            ]
        ]
    )


def manual_payment_keyboard(
    payment_id: int
) -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Я оплатил",
                    callback_data=f"manual_paid:{payment_id}"
                )
            ]
        ]
    )


def admin_manual_payment_keyboard(
    payment_id: int
) -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"manual_confirm:{payment_id}"
                ),

                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"manual_reject:{payment_id}"
                ),
            ]
        ]
    )


def seeker_feedback_keyboard() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="✅ Я нашёл работу через бота",
                    callback_data="found_work"
                )
            ],

            [
                InlineKeyboardButton(
                    text="⭐ Купить VIP — 300 ₸",
                    callback_data=f"manual:{FEATURE_VIP_SEEKER}"
                )
            ],
        ]
    )


def employer_feedback_keyboard(
    vacancy_id: int | None = None
) -> InlineKeyboardMarkup:

    rows = []

    if vacancy_id:
        rows.append([
            InlineKeyboardButton(
                text="✅ Я закрыл вакансию через бота",
                callback_data=f"close_vacancy:{vacancy_id}"
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="📌 Закрепить вакансию — 300 ₸",
            callback_data=f"manual:{FEATURE_PIN_VACANCY}:{vacancy_id}"
        )
    ])

    rows.append([
        InlineKeyboardButton(
            text="🚀 Срочная рассылка — 200 ₸",
            callback_data=f"manual:{FEATURE_URGENT_BROADCAST}:{vacancy_id}"
        )
    ])

    rows.append([
        InlineKeyboardButton(
            text="♾ Купить безлимит — 500 ₸",
            callback_data=f"manual:{FEATURE_UNLIMITED_VACANCIES}"
        )
    ])

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def feedback_keyboard(
    latest_vacancy_id: int | None = None
) -> InlineKeyboardMarkup:

    if latest_vacancy_id:
        return employer_feedback_keyboard(
            latest_vacancy_id
        )

    return seeker_feedback_keyboard()


def channel_post_keyboard(
    vacancy_id: int,
    bot_username: str
) -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="📩 Откликнуться",
                    url=f"https://t.me/{bot_username}?start=apply_{vacancy_id}"
                ),
            ],

            [
                InlineKeyboardButton(
                    text="🎁 Получить ссылку для бонусов",
                    url=f"https://t.me/{bot_username}?start=share_{vacancy_id}"
                ),
            ],

            [
                InlineKeyboardButton(
                    text="🙈 Скрыть",
                    callback_data=f"hide_post:{vacancy_id}"
                ),
            ],
        ]
    )


def weekly_stats_keyboard(
    bot_username: str
) -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="📝 Заполнить анкету",
                    url=f"https://t.me/{bot_username}?start=resume"
                ),
            ],

            [
                InlineKeyboardButton(
                    text="📢 Разместить вакансию",
                    url=f"https://t.me/{bot_username}?start=vacancy"
                ),
            ],

            [
                InlineKeyboardButton(
                    text="📤 Поделиться",
                    switch_inline_query="Работа Лисаковск"
                ),
            ],
        ]
    )



def employer_candidates_keyboard(
    vacancy_id: int
) -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👀 Кандидаты",
                    callback_data=f"view_candidates:{vacancy_id}"
                )
            ]
        ]
    )

def seeker_cabinet_keyboard() -> ReplyKeyboardMarkup:

    return ReplyKeyboardMarkup(
        keyboard=[

            [
                KeyboardButton(
                    text="📝 Моя анкета"
                )
            ],

            [
                KeyboardButton(
                    text="📈 Продвигать анкету"
                )
            ],

            [
                KeyboardButton(
                    text="👥 Пригласить друга"
                )
            ],

            [
                KeyboardButton(
                    text="⬅️ Назад"
                )
            ],

        ],
        resize_keyboard=True,
    )


def employer_cabinet_keyboard() -> ReplyKeyboardMarkup:

    return ReplyKeyboardMarkup(
        keyboard=[

            [
                KeyboardButton(
                    text="🏢 Моя компания"
                ),
                KeyboardButton(
                    text="📋 Мои вакансии"
                )
            ],

            [
                KeyboardButton(
                    text="📺 Лента вакансий"
                )
            ],

            [
                KeyboardButton(
                    text="⬅️ Назад"
                )
            ],

        ],
        resize_keyboard=True,
    )


def company_keyboard() -> ReplyKeyboardMarkup:

    return ReplyKeyboardMarkup(
        keyboard=[

            [
                KeyboardButton(
                    text="✏️ Редактировать"
                )
            ],

            [
                KeyboardButton(
                    text="⬅️ Назад"
                )
            ],

        ],
        resize_keyboard=True,
    )


def company_start_keyboard() -> ReplyKeyboardMarkup:

    return ReplyKeyboardMarkup(
        keyboard=[

            [
                KeyboardButton(
                    text="✅ Создать карточку компании"
                )
            ],

            [
                KeyboardButton(
                    text="⏭ Продолжить без карточки"
                )
            ],

            [
                KeyboardButton(
                    text="⬅️ Назад"
                )
            ],

        ],
        resize_keyboard=True,
    )


def continue_keyboard() -> ReplyKeyboardMarkup:

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="✅ Продолжить"
                )
            ]
        ],
        resize_keyboard=True
    )

def skip_keyboard() -> ReplyKeyboardMarkup:

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="⏭ Пропустить"
                )
            ]
        ],
        resize_keyboard=True
    )


def city_keyboard() -> ReplyKeyboardMarkup:

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="🏠 Удалённо"
                )
            ],
            [
                KeyboardButton(
                    text="⏭ Пропустить"
                )
            ]
        ],
        resize_keyboard=True
    )

def contacts_keyboard() -> ReplyKeyboardMarkup:

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="Telegram"
                )
            ],
            [
                KeyboardButton(
                    text="WhatsApp"
                )
            ],
            [
                KeyboardButton(
                    text="Телефон"
                )
            ],
            [
                KeyboardButton(
                    text="Любой способ"
                )
            ],
            [
                KeyboardButton(
                    text="⏭ Пропустить"
                )
            ]
        ],
        resize_keyboard=True
    )

def employer_vacancy_keyboard(
    vacancy_id: int
) -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="📨 Отклики",
                    callback_data=f"view_candidates:{vacancy_id}"
                )
            ],

            [
                InlineKeyboardButton(
                    text="✏️ Редактировать",
                    callback_data=f"edit_vacancy:{vacancy_id}"
                ),

                InlineKeyboardButton(
                    text="🔒 Закрыть",
                    callback_data=f"close_vacancy:{vacancy_id}"
                )
            ],

            [
                InlineKeyboardButton(
                    text="🚀 Продвигать",
                    callback_data=f"promote_vacancy:{vacancy_id}"
                )
            ]
        ]
    )


def edit_vacancy_keyboard(
    vacancy_id: int
) -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="💼 Название",
                    callback_data=f"edit_title:{vacancy_id}"
                )
            ],

            [
                InlineKeyboardButton(
                    text="💰 Зарплата",
                    callback_data=f"edit_salary:{vacancy_id}"
                )
            ],

            [
                InlineKeyboardButton(
                    text="🕒 График",
                    callback_data=f"edit_schedule:{vacancy_id}"
                )
            ],

            [
                InlineKeyboardButton(
                    text="📋 Описание",
                    callback_data=f"edit_description:{vacancy_id}"
                )
            ],

            [
                InlineKeyboardButton(
                    text="📞 Контакты",
                    callback_data=f"edit_contacts:{vacancy_id}"
                )
            ]
        ]
    )


def confirm_vacancy_edit_keyboard() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="✅ Сохранить",
                    callback_data="confirm_vacancy_edit"
                )
            ],

            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="cancel_vacancy_edit"
                )
            ]
        ]
    )


def confirm_salary_edit_keyboard() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="✅ Сохранить",
                    callback_data="confirm_salary_edit"
                )
            ],

            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="cancel_salary_edit"
                )
            ]
        ]
    )


def confirm_contacts_edit_keyboard() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="✅ Сохранить",
                    callback_data="confirm_contacts_edit"
                )
            ],

            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="cancel_contacts_edit"
                )
            ]
        ]
    )



def confirm_schedule_edit_keyboard() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="✅ Сохранить",
                    callback_data="confirm_schedule_edit"
                )
            ],

            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="cancel_schedule_edit"
                )
            ]
        ]
    )


def confirm_title_edit_keyboard() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="✅ Сохранить",
                    callback_data="confirm_title_edit"
                )
            ],

            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="cancel_title_edit"
                )
            ]
        ]
    )



def candidate_preview_keyboard(
    seeker_id: int
) -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👀 Подробнее",
                    callback_data=f"candidate:{seeker_id}"
                )
            ]
        ]
    )


def candidate_preview_keyboard(
    seeker_id: int
) -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👀 Подробнее",
                    callback_data=f"candidate:{seeker_id}"
                )
            ]
        ]
    )


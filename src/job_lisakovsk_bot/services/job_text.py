from __future__ import annotations

from datetime import datetime


def format_salary(
    salary_min: int | None,
    salary_max: int | None
) -> str:

    if salary_min is None and salary_max is None:
        return "Не важно"

    if (
        salary_min is not None
        and salary_max is not None
    ):

        if salary_min == salary_max:
            return f"от {salary_min} тыс. тг."

        return f"{salary_min}-{salary_max} тыс. тг."

    if salary_min is not None:
        return f"от {salary_min} тыс. тг."

    return f"до {salary_max} тыс. тг."


MONTHS = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}


def vacancy_public_text(vacancy: dict, bot_username: str) -> str:
    title = vacancy["title"]

    company_name = (
        vacancy.get("company_name")
        or "Работодатель"
    )

    salary = format_salary(
        vacancy.get("salary_min"),
        vacancy.get("salary_max")
    )

    schedule = vacancy["schedule"].lower()
    description = vacancy["description"]
    contacts = vacancy["contacts"]
    now = datetime.now()

    month_tag = (
        f"#{MONTHS[now.month]}{now.year}@LisakovskHub"
    )

    return (
        f"🏢 <b>Компания</b>\n"
        f"{company_name}\n\n"

        f"💼 <b>Вакансия</b>\n"
        f"{title}\n\n"

        f"📍 <b>Место работы</b>\n"
        f"{vacancy.get('location') or 'Не указано'}\n\n"

        f"💰 <b>Зарплата</b>\n"
        f"{salary}\n\n"

        f"🕒 <b>График</b>\n"
        f"{schedule.capitalize()}\n\n"

        f"📋 <b>Обязанности</b>\n"
        f"{description}\n\n"

        f"📞 <b>Контакты</b>\n"
        f"{contacts}\n\n"

        f"{month_tag} #Работа@LisakovskHub\n\n"

        f"Разместить свою вакансию:\n"
        f"@{bot_username}"
    )


def vacancy_private_text(vacancy: dict, bot_username: str) -> str:
    return (
        vacancy_public_text(vacancy, bot_username)
        + "\n\nЕсли вакансия интересна — нажмите «Откликнуться»."
    )


def seeker_card(seeker: dict, number: int | None = None) -> str:
    prefix = f"Соискатель #{number}" if number is not None else "Соискатель"

    salary = format_salary(
        seeker.get("salary_min"),
        seeker.get("salary_max")
    )

    return (
        f"{prefix}\n"
        f"Сфера: {seeker['sphere']}\n"
        f"График: {seeker['schedule']}\n"
        f"Зарплата: {salary}\n"
        f"О себе: {seeker['about']}"
    )


def admin_stats_text(stats: dict) -> str:
    return (
        "📊 Админ-статистика\n\n"
        f"Соискателей в базе: {stats['seekers_total']}\n"
        f"Активных вакансий: {stats['active_vacancies']}\n"
        f"Закрыто вакансий: {stats['closed_vacancies']}\n"
        f"Нашли работу через бота: {stats['found_work']}\n"
        f"👥 Рефералов: {stats['referrals_total']}\n"
        f"Платных пользователей: {stats['paid_users']}\n"
        f"Заработано Stars: {stats['stars_earned']}"
    )


def employer_stats_text(stats: dict) -> str:
    return (
        "📈 Ваш кабинет работодателя\n\n"
        f"Размещено вакансий: {stats['vacancies_total']}\n"
        f"Просмотров: {stats['views']}\n"
        f"Откликов: {stats['responses']}\n"
        f"Закрыто вакансий: {stats['closed_vacancies']}\n"
        f"Соискателей в вашей сфере: {stats['seekers_in_sphere']}"
    )


def seeker_stats_text(stats: dict) -> str:
    status = (
        f"VIP до {stats['vip_until']}"
        if stats.get("vip_until")
        else "Обычный"
    )

    created_at = (
        stats.get("created_at")
        or "анкета ещё не создана"
    )

    return (
        "👤 Ваш кабинет соискателя\n\n"
        f"Дата создания анкеты: {created_at}\n"
        f"Просмотров работодателями: {stats['views']}\n"
        f"Откликов отправлено: {stats['responses']}\n"
        f"Приглашено друзей: {stats['referrals']}\n"
        f"Текущий статус: {status}"
    )


def weekly_stats_text(stats: dict) -> str:
    top_employers = (
        stats.get("top_employers")
        or ["пока нет данных"]
    )

    return (
        "📊 Итоги недели в «Работа Лисаковск»\n\n"
        f"Новых соискателей: {stats['new_seekers']}\n"
        f"Новых вакансий: {stats['new_vacancies']}\n"
        f"Нашли работу через бота: {stats['found_work']}\n"
        f"Самая популярная сфера: {stats['popular_sphere']}\n"
        "Топ-3 работодателя по откликам:\n- "
        + "\n- ".join(top_employers)
    )

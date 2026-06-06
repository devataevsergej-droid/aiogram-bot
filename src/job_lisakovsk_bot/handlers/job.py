from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from aiogram.fsm.storage.base import StorageKey

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, ForceReply, Message


from job_lisakovsk_bot.config import Settings
from job_lisakovsk_bot.constants import (
    FEATURE_PIN_VACANCY,
    FEATURE_UNLIMITED_VACANCIES,
    FEATURE_URGENT_BROADCAST,
    FEATURE_VIP_SEEKER,
    PAYMENT_TYPE_MANUAL,
)
from job_lisakovsk_bot.db import SupabaseRepository
from job_lisakovsk_bot.keyboards.job_inline import (
    employer_candidates_keyboard,
    admin_manual_payment_keyboard,
    buy_unlimited_keyboard,
    channel_post_keyboard,
    employer_feedback_keyboard,
    employer_cabinet_keyboard,
    main_menu,
    manual_payment_keyboard,
    moderation_keyboard,
    schedules_keyboard,
    seeker_cabinet_keyboard,
    seeker_feedback_keyboard,
    seeker_vip_keyboard,
    spheres_keyboard,
    vacancies_keyboard,
    vacancy_responded_keyboard,
    vacancy_paid_features_keyboard,
)
from job_lisakovsk_bot.services.job_text import (
    admin_stats_text,
    employer_stats_text,
    seeker_card,
    seeker_stats_text,
    vacancy_private_text,
    vacancy_public_text,
    format_salary,
)
from job_lisakovsk_bot.services.limits import (
    can_create_vacancy,
    can_send_notification,
    has_free_monthly_urgent,
    has_free_vip_bonus,
)
from job_lisakovsk_bot.services.payments import get_feature_request
from job_lisakovsk_bot.services.referrals import parse_referral_arg, referral_bonus_text, referral_deep_link
from job_lisakovsk_bot.services.salary import parse_salary_range
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from pathlib import Path
from random import choice

from aiogram.types import FSInputFile

ASSETS_DIR = (
    Path(__file__).resolve().parent.parent / "assets"
)

SHARE_BANNERS = [
    ASSETS_DIR / "banner_1.png",
    ASSETS_DIR / "banner_2.png",
    ASSETS_DIR / "banner_3.png",
    ASSETS_DIR / "banner_4.png",
]

logger = logging.getLogger(__name__)
router = Router(name="job")

@router.message(Command("test"))
async def test_command(message: Message):
    await message.answer("✅ Бот работает, хендлеры зарегистрированы")

async def get_user_role(
    user_id: int,
    repo: SupabaseRepository
) -> str | None:

    active_role = await repo.get_user_active_role(
        user_id
    )

    if active_role:
        return active_role.get("role")

    vacancies = await repo.list_employer_vacancies(
        user_id
    )

    if vacancies:
        return "employer"

    seeker = await repo.get_seeker(
        user_id
    )

    if seeker:
        return "seeker"

    return None


@router.message(F.text == "🔄 Переключиться на соискателя")
@router.message(F.text == "🔄 Переключиться на работодателя")
async def toggle_role(message: Message, repo: SupabaseRepository):

    current_role = await get_user_role(
        message.from_user.id,
        repo
    )

    if not current_role:

        await message.answer(
            "❌ Сначала создайте вакансию "
            "или заполните анкету."
        )

        return

    new_role = (
        "seeker"
        if current_role == "employer"
        else "employer"
    )

    await repo.set_user_active_role(
        message.from_user.id,
        new_role
    )

    role_name = (
        "Соискатель"
        if new_role == "seeker"
        else "Работодатель"
    )

    await message.answer(
        f"✅ Теперь ваш режим:\n\n"
        f"👤 {role_name}",

        reply_markup=main_menu(
            user_role=new_role
        )
    )


class SeekerForm(StatesGroup):

    intro = State()

    full_name = State()
    age = State()
    phone = State()

    desired_positions = State()
    skills = State()

    salary = State()
    schedule = State()

    rotation_work = State()
    driver_license = State()

    city = State()

    about = State()

    contacts = State()

    confirm = State()

    # legacy
    sphere = State()


class VacancyForm(StatesGroup):
    company_name = State()
    title = State()
    sphere = State()
    schedule = State()
    salary = State()
    contacts = State()
    description = State()
    waiting_payment_check = State()


class RejectVacancyForm(StatesGroup):
    reason = State()

class AdminSettingsForm(StatesGroup):
    waiting_for_price = State()
    waiting_for_phone = State()

class PinDaysForm(StatesGroup):
    waiting_for_days = State()


async def send_vacancy_notifications(
    *,
    repo: SupabaseRepository,
    bot: Bot,
    settings: Settings,
    vacancy: dict,
    seekers: list[dict],
    enforce_limits: bool = True,
) -> int:
    sent = 0
    for seeker in seekers:
        if enforce_limits:
            usage = await repo.get_or_create_usage(seeker["user_id"])
            referrals = await repo.count_referrals(seeker["user_id"])
            decision = can_send_notification(int(usage.get("notifications_today") or 0), referrals)
            if not decision.allowed:
                continue
        try:
            await bot.send_message(
                seeker["user_id"],
                vacancy_private_text(vacancy, settings.bot_username),
                reply_markup=vacancies_keyboard(vacancy["id"]),
            )
            await repo.record_notification(vacancy["id"], seeker["user_id"])
            await repo.increment_notifications_today(seeker["user_id"])
            sent += 1
        except Exception:
            continue
    return sent


async def fulfill_paid_feature(
    *,
    repo: SupabaseRepository,
    bot: Bot,
    settings: Settings,
    user_id: int,
    feature: str,
    vacancy_id: int | None = None,
) -> str:
    if feature == FEATURE_UNLIMITED_VACANCIES:
        return "✅ Безлимит вакансий активирован на месяц."

    if feature == FEATURE_VIP_SEEKER:
        await repo.activate_vip(user_id)
        return "⭐ VIP-статус соискателя активирован на месяц."

    if vacancy_id is None:
        return "❌ Оплата получена, но вакансия не указана. Напишите администратору."

    vacancy = await repo.get_vacancy(vacancy_id)
    if not vacancy:
        return "❌ Оплата получена, но вакансия не найдена. Напишите администратору."

    if feature == FEATURE_PIN_VACANCY:
        if not vacancy.get("channel_message_id"):
            return "❌ Оплата получена, но вакансия ещё не опубликована в канале."
        
        # Получаем количество дней из переданных параметров
        pin_days = 3
        
        await bot.pin_chat_message(settings.channel_id, vacancy["channel_message_id"], disable_notification=True)
        await repo.schedule_unpin(vacancy_id, vacancy["channel_message_id"], datetime.now(UTC) + timedelta(days=pin_days))
        return f"📌 Вакансия закреплена в канале на {pin_days} дней."

    if feature == FEATURE_URGENT_BROADCAST:
        seekers = await repo.list_all_active_seekers()
        sent = await send_vacancy_notifications(
            repo=repo,
            bot=bot,
            settings=settings,
            vacancy=vacancy,
            seekers=seekers,
            enforce_limits=False,
        )
        await repo.increment_urgent_broadcasts_this_month(user_id)
        return f"🚀 Срочная рассылка выполнена. Отправлено уведомлений: {sent}."

    return "✅ Оплата получена."


@router.message(CommandStart())
async def start(
    message: Message,
    state: FSMContext,
    command: CommandObject,
    repo: SupabaseRepository,
    settings: Settings,
    bot: Bot,
) -> None:

    arg = command.args
    await message.answer(f"DEBUG ARG: {arg}")

    referrer_id = parse_referral_arg(arg)

    if referrer_id is not None:

        await repo.register_referral(
            referrer_id,
            message.from_user.id
        )

        await message.answer(
            "🎉 Реферальная ссылка учтена!\n\n"
            "Добро пожаловать в «Работа Лисаковск»!\n\n"
            "Выберите действие в меню ниже 👇",

            reply_markup=main_menu(
    user_role="seeker"
)
        )

        return

    # Отклик на вакансию
    if arg and arg.startswith("apply_"):

        vacancy_id = int(arg.split("_")[1])

        await apply_vacancy_start(
            message,
            vacancy_id,
            repo,
            settings,
            bot
        )

        return

    # Просмотр вакансии
    if arg and arg.startswith("vacancy_"):

        vacancy_id = int(arg.split("_")[1])

        vacancy = await repo.get_vacancy(
            vacancy_id
        )

        if not vacancy:

            await message.answer(
                "❌ Вакансия не найдена."
            )

            return

        await message.answer(
            vacancy_public_text(
                vacancy,
                settings.bot_username
            ),

            reply_markup=channel_post_keyboard(
                vacancy_id,
                settings.bot_username
            )
        )

        return

    # Получение referral ссылки
    if arg and arg.startswith("share_"):

        vacancy_id = int(arg.split("_")[1])

        banner = choice(SHARE_BANNERS)

        banner_name = banner.stem

        if banner_name.endswith("1"):
            banner_code = "b1"
        elif banner_name.endswith("2"):
            banner_code = "b2"
        elif banner_name.endswith("3"):
            banner_code = "b3"
        elif banner_name.endswith("4"):
            banner_code = "b4"
        else:
            banner_code = "b0"

        referral_link = (
            f"https://t.me/{settings.bot_username}"
            f"?start={banner_code}_r{message.from_user.id}"
        )

        await message.answer_photo(
            photo=FSInputFile(str(banner)),
            caption=
                "📢 Делитесь проектом и получайте бонусные показы!\n\n"
                "Лучше всего работают статусы и истории.\n\n"
                "Сохраните баннер и разместите его там, где вас читают 👇"
        )

        await message.answer(
            "🎁 Ваша персональная ссылка для приглашений:\n\n"

            f"{referral_link}\n\n"

            "📢 Сохраните баннер и разместите его:\n"
            "• в статусе WhatsApp\n"
            "• в Telegram Stories\n"
            "• в Instagram Stories\n"
            "• в Одноклассниках\n"
            "• в городских чатах и группах\n\n"

            "👥 За новых пользователей начисляются бонусные показы."
        )

        return

    # Быстрый старт анкеты
    if arg == "resume":

        await seeker_start(
            message,
            state
        )

        return

    # Быстрый старт вакансии
    if arg == "vacancy":

        await vacancy_start(
            message,
            state
        )

        return

    # Определяем роль пользователя
    user_role = await get_user_role(
        message.from_user.id,
        repo
    )

    # Главное приветствие
    await message.answer(
        "👋 Добро пожаловать в «Работа Лисаковск»!\n\n"

        "📌 Соискатель — заполните анкету "
        "и получайте подходящие вакансии\n\n"

        "📢 Работодатель — размещайте вакансии "
        "и находите сотрудников\n\n"

        "👇 Выберите действие:",

        reply_markup=main_menu(user_role)
    )


@router.message(Command("resume"))
async def cmd_resume(
    message: Message,
    state: FSMContext
):

    await seeker_start(
        message,
        state
    )


@router.message(Command("vacancy"))
async def cmd_vacancy(
    message: Message,
    state: FSMContext
):

    await vacancy_start(
        message,
        state
    )


async def apply_vacancy_start(
    message: Message,
    vacancy_id: int,
    repo: SupabaseRepository,
    settings: Settings,
    bot: Bot
) -> None:

    try:

        seeker = await repo.get_seeker(
            message.from_user.id
        )

        vacancy = await repo.get_vacancy(
            vacancy_id
        )

        if not vacancy or vacancy["status"] != "approved":

            await message.answer(
                "❌ Вакансия не найдена или уже закрыта."
            )

            return

        if not seeker:

            await message.answer(
                "🔍 Чтобы откликнуться, "
                "сначала заполните анкету соискателя.\n\n"

                "Нажмите кнопку "
                "«📝 Заполнить анкету» "
                "в меню ниже 👇",

                reply_markup=main_menu()
            )

            return

        await message.answer(
            vacancy_private_text(
                vacancy,
                settings.bot_username
            ),

            reply_markup=vacancies_keyboard(
                vacancy_id
            )
        )

    except Exception as e:

        logger.error(
            f"Error in apply_vacancy_start: {e}"
        )

        await message.answer(
            "❌ Произошла ошибка. Попробуйте позже."
        )


@router.message(F.text == "📝 Заполнить анкету")
async def seeker_start(
    message: Message,
    state: FSMContext
) -> None:

    await state.clear()

    await state.set_state(
        SeekerForm.intro
    )

    await message.answer(
        "⚠️ Важно!\n\n"
        "Качество подбора вакансий зависит прежде всего от двух полей:\n\n"
        "🎯 Желаемые должности\n"
        "🏷 Ключевые навыки\n\n"
        "Именно по ним система:\n"
        "• подбирает вакансии\n"
        "• рекомендует вашу анкету работодателям\n"
        "• делает рассылки\n"
        "• показывает подходящие предложения\n\n"
        "❗ Указывайте несколько вариантов через запятую.\n\n"
        "Например:\n"
        "Продавец, Кассир, Администратор\n\n"
        "Нажмите:\n"
        "Продолжить"
    )


@router.message(
    SeekerForm.intro,
    F.text.casefold() == "продолжить"
)
async def seeker_intro_continue(
    message: Message,
    state: FSMContext
) -> None:

    await state.set_state(
        SeekerForm.full_name
    )

    await message.answer(
        "👤 Как к вам обращаться?"
    )


@router.message(SeekerForm.full_name)
async def seeker_full_name(
    message: Message,
    state: FSMContext
) -> None:

    await state.update_data(
        full_name=(message.text or "").strip()
    )

    await state.set_state(
        SeekerForm.age
    )

    await message.answer(
        "🎂 Сколько вам лет?\n\n"
        "Например:\n"
        "18\n"
        "25\n"
        "42"
    )

@router.message(SeekerForm.age)
async def seeker_age(
    message: Message,
    state: FSMContext
) -> None:

    try:

        age = int(message.text)

        if age < 14 or age > 100:

            await message.answer(
                "❌ Укажите возраст числом от 14 до 100."
            )

            return

        await state.update_data(
            age=age
        )

        await state.set_state(
            SeekerForm.phone
        )

        await message.answer(
            "📱 Укажите номер телефона для связи.\n\n"
            "Например:\n"
            "87775556644"
        )

    except ValueError:

        await message.answer(
            "❌ Возраст нужно указать числом.\n\n"
            "Например:\n"
            "25"
        )


@router.message(SeekerForm.phone)
async def seeker_phone(
    message: Message,
    state: FSMContext
) -> None:

    phone = (message.text or "").strip()

    if len(phone) < 10:

        await message.answer(
            "❌ Укажите корректный номер телефона."
        )

        return

    await state.update_data(
        phone=phone
    )

    await state.set_state(
        SeekerForm.desired_positions
    )

    await message.answer(
        "🎯 Желаемые должности\n\n"
        "Укажите несколько вариантов через запятую.\n\n"
        "Например:\n"
        "Продавец, Кассир, Администратор"
    )


@router.message(SeekerForm.desired_positions)
async def seeker_desired_positions(
    message: Message,
    state: FSMContext
) -> None:

    text = (message.text or "").strip()

    bad_values = {
        "любая",
        "любая работа",
        "ищу работу",
        "без разницы"
    }

    if text.lower() in bad_values:

        await message.answer(
            "⚠️ Укажите конкретные должности.\n\n"
            "Например:\n"
            "Продавец, Кассир, Администратор"
        )

        return

    await state.update_data(
        desired_positions=text
    )

    await state.set_state(
        SeekerForm.skills
    )

    await message.answer(
        "🏷 Ключевые навыки\n\n"
        "Укажите навыки через запятую.\n\n"
        "Например:\n"
        "1С, Excel, Продажи, Работа с клиентами"
    )

@router.message(SeekerForm.skills)
async def seeker_skills(
    message: Message,
    state: FSMContext
) -> None:

    text = (message.text or "").strip()

    bad_values = {
        "есть опыт",
        "все умею",
        "всё умею",
        "много чего"
    }

    if text.lower() in bad_values:

        await message.answer(
            "⚠️ Перечислите конкретные навыки.\n\n"
            "Например:\n"
            "1С, Excel, Продажи"
        )

        return

    await state.update_data(
        skills=text
    )

    await state.set_state(
        SeekerForm.salary
    )

    await message.answer(
        "💰 Укажите желаемую зарплату.\n\n"
        "Например:\n"
        "250000\n"
        "300000\n\n"
        "Или напишите:\n"
        "Пропустить"
    )



#@router.message(SeekerForm.contacts)
#async def seeker_contacts(
#    message: Message,
#    state: FSMContext
#) -> None:
#
#    await state.update_data(
#        contacts=message.text
#    )
#
#    await state.set_state(
#        SeekerForm.sphere
#    )
#
#    await message.answer(
#        "📂 Выберите сферу:",
#        reply_markup=spheres_keyboard(
#            "seeker_sphere"
#        )
#    )


@router.callback_query(SeekerForm.sphere, F.data.startswith("seeker_sphere:"))
async def seeker_sphere(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(sphere=callback.data.split(":", 1)[1])
    await state.set_state(SeekerForm.schedule)
    await callback.message.edit_text("📅 Выберите график:", reply_markup=schedules_keyboard("seeker_schedule"))
    await callback.answer()


@router.message(SeekerForm.schedule)
async def seeker_schedule(
    message: Message,
    state: FSMContext
) -> None:

    schedule = (message.text or "").strip()

    await state.update_data(
        schedule=schedule
    )

    await state.set_state(
        SeekerForm.rotation_work
    )

    await message.answer(
        "🚗 Готовы работать вахтовым методом?\n\n"
        "Ответьте:\n"
        "Да\n"
        "Нет\n"
        "Рассмотрю"
    )

@router.message(SeekerForm.rotation_work)
async def seeker_rotation_work(
    message: Message,
    state: FSMContext
) -> None:

    value = (message.text or "").strip()

    await state.update_data(
        rotation_work=value
    )

    await state.set_state(
        SeekerForm.driver_license
    )

    await message.answer(
        "🚘 Есть водительское удостоверение?\n\n"
        "Например:\n"
        "Нет\n"
        "Категория B\n"
        "Категория C\n"
        "Категория CE"
    )

@router.message(SeekerForm.driver_license)
async def seeker_driver_license(
    message: Message,
    state: FSMContext
) -> None:

    await state.update_data(
        driver_license=(message.text or "").strip()
    )

    await state.set_state(
        SeekerForm.city
    )

    await message.answer(
        "📍 В каком городе вы ищете работу?\n\n"
        "Например:\n"
        "Лисаковск"
    )

@router.message(SeekerForm.city)
async def seeker_city(
    message: Message,
    state: FSMContext
) -> None:

    await state.update_data(
        city=(message.text or "").strip()
    )

    await state.set_state(
        SeekerForm.about
    )

    await message.answer(
        "📝 Расскажите немного о себе.\n\n"
        "Опыт работы, сильные стороны,\n"
        "дополнительная информация."
    )



@router.message(SeekerForm.salary)
async def seeker_salary(
    message: Message,
    state: FSMContext
) -> None:

    text = (message.text or "").strip()

    if text.lower() == "пропустить":

        await state.update_data(
            salary_min=None,
            salary_max=None
        )

    else:

        try:

            salary = int(
                text.replace(" ", "")
            )

            if salary < 50000:

                await message.answer(
                    "❌ Укажите зарплату числом.\n\n"
                    "Например:\n"
                    "250000"
                )

                return

            await state.update_data(
                salary_min=salary,
                salary_max=salary
            )

        except ValueError:

            await message.answer(
                "❌ Укажите зарплату числом.\n\n"
                "Например:\n"
                "250000\n\n"
                "Или напишите:\n"
                "Пропустить"
            )

            return

    await state.set_state(
        SeekerForm.schedule
    )

    await message.answer(
        "🕒 Какой график вас интересует?\n\n"
        "Например:\n"
        "Полный день\n"
        "Сменный\n"
        "Гибкий\n"
        "Удалённо"
    )

@router.message(SeekerForm.about)
async def seeker_about(
    message: Message,
    state: FSMContext
) -> None:

    await state.update_data(
        about=(message.text or "").strip()
    )

    await state.set_state(
        SeekerForm.contacts
    )

    await message.answer(
        "📞 Как с вами удобнее связаться?\n\n"
        "Например:\n"
        "WhatsApp\n"
        "Telegram\n"
        "Телефон\n"
        "Любой способ"
    )

@router.message(SeekerForm.contacts)
async def seeker_contacts_finish(
    message: Message,
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    try:

        await state.update_data(
            contacts=(message.text or "").strip()
        )

        data = await state.get_data()

        payload = {
            "user_id": message.from_user.id,
            "username": message.from_user.username,

            "full_name": data.get("full_name"),
            "age": data.get("age"),
            "phone": data.get("phone"),

            "desired_positions": data.get("desired_positions"),
            "skills": data.get("skills"),

            "salary_min": data.get("salary_min"),
            "salary_max": data.get("salary_max"),

            "schedule": data.get("schedule"),

            "rotation_work": data.get("rotation_work"),
            "driver_license": data.get("driver_license"),

            "city": data.get("city"),

            "about": data.get("about"),
            "contacts": data.get("contacts"),

            "active": True,
            "profile_completed": True,
        }

        await repo.upsert_seeker(
            payload
        )

        await repo.set_user_active_role(
            message.from_user.id,
            "seeker"
        )

        await state.clear()

        await message.answer(
            "✅ Анкета успешно сохранена.",
            reply_markup=main_menu(
                user_role="seeker"
            )
        )

    except Exception as e:

        logger.error(
            f"Error in seeker_contacts_finish: {e}"
        )

        await message.answer(
            "❌ Ошибка при сохранении анкеты."
        )


"""
# @router.message(F.text.in_({"🔍 Смотреть вакансии", "/vacancies"}))
async def show_vacancies(
    message: Message,
    repo: SupabaseRepository,
    settings: Settings
) -> None:

    try:

        vacancies = await repo.list_active_vacancies()

        if not vacancies:

            await message.answer(
                "📭 Пока активных вакансий нет."
            )

            return

        for vacancy in vacancies:

            await message.answer(
                vacancy_private_text(
                    vacancy,
                    settings.bot_username
                ),

                reply_markup=vacancies_keyboard(
                    vacancy["id"]
                ),
            )

    except Exception as e:

        logger.error(
            f"Error in show_vacancies: {e}"
        )

        await message.answer(
            "❌ Ошибка при загрузке вакансий."
        )
        """


@router.message(F.text == "📢 Разместить вакансию")
async def vacancy_start(
    message: Message,
    state: FSMContext
) -> None:

    await state.clear()

    await state.set_state(
        VacancyForm.company_name
    )

    await message.answer(
        "🏢 Укажите название организации.\n\n"
        "Например:\n"
        "ТОО Рога и Копыта\n"
        "Магазин «Уют»\n"
        "Салон красоты Beauty\n"
        "ИП Иванов"
    )


@router.message(VacancyForm.company_name)
async def vacancy_company_name(
    message: Message,
    state: FSMContext
) -> None:

    await state.update_data(
        company_name=message.text
    )

    await state.set_state(
        VacancyForm.title
    )

    await message.answer(
        "👔 Кого ищете?\n\n"
        "Напишите должность или услугу.\n\n"
        "Например:\n"
        "Сварщик\n"
        "Бариста\n"
        "Менеджер по продажам"
    )


@router.message(VacancyForm.title)
async def vacancy_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=(message.text or "").strip())
    await state.set_state(VacancyForm.sphere)
    await message.answer("📂 Выберите сферу:", reply_markup=spheres_keyboard("vacancy_sphere"))


@router.callback_query(VacancyForm.sphere, F.data.startswith("vacancy_sphere:"))
async def vacancy_sphere(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(sphere=callback.data.split(":", 1)[1])
    await state.set_state(VacancyForm.schedule)
    await callback.message.edit_text("📅 Выберите график:", reply_markup=schedules_keyboard("vacancy_schedule"))
    await callback.answer()


@router.callback_query(VacancyForm.schedule, F.data.startswith("vacancy_schedule:"))
async def vacancy_schedule(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(schedule=callback.data.split(":", 1)[1])
    await state.set_state(VacancyForm.salary)

    await callback.message.edit_text(
        "💰 Укажите зарплату в тысячах тенге.\n\n"
        "Примеры:\n"
        "200\n"
        "350\n"
        "500\n\n"
        "Или диапазон:\n"
        "200-300\n"
        "350-500"
    )

    await callback.answer()


@router.message(VacancyForm.salary)
async def vacancy_salary(message: Message, state: FSMContext) -> None:

    text = (message.text or "").strip()

    if " " in text and "-" not in text:
        await message.answer(
            "❌ Не понял сумму.\n\n"
            "Введите зарплату в тысячах тенге.\n\n"
            "Примеры:\n"
            "200\n"
            "350\n"
            "500\n\n"
            "Или диапазон:\n"
            "200-300\n"
            "350-500"
        )
        return

    try:
        salary_min, salary_max = parse_salary_range(text)

    except ValueError:
        await message.answer(
            "❌ Не понял сумму.\n\n"
            "Введите зарплату в тысячах тенге.\n\n"
            "Примеры:\n"
            "200\n"
            "350\n"
            "500\n\n"
            "Или диапазон:\n"
            "200-300\n"
            "350-500"
        )
        return

    await state.update_data(
        salary_min=salary_min,
        salary_max=salary_max
    )

    await state.set_state(VacancyForm.contacts)

    await message.answer(
        "📞 Как с вами связаться?\n\n"
        "Укажите телефон, мессенджер и удобное время для связи.\n\n"
        "Например:\n"
        "87771234567\n"
        "WhatsApp\n"
        "с 09:00 до 18:00"
    )


@router.message(VacancyForm.contacts)
async def vacancy_contacts(message: Message, state: FSMContext) -> None:
    await state.update_data(
        contacts=(message.text or "").strip()
    )

    await state.set_state(VacancyForm.description)

    await message.answer(
        "📝 Опишите, что требуется от кандидата."
    )


@router.message(VacancyForm.description)
async def vacancy_description(
    message: Message,
    state: FSMContext,
    repo: SupabaseRepository,
    settings: Settings,
    bot: Bot,
) -> None:

    try:
        data = await state.get_data()

        referred_by = await repo.get_referrer_for_user(
            message.from_user.id
        )

        payload = {
            "employer_id": message.from_user.id,
            "employer_username": message.from_user.username,

            "company_name": data["company_name"],

            "title": data["title"],
            "sphere": data["sphere"],
            "schedule": data["schedule"],
            "salary_min": data["salary_min"],
            "salary_max": data["salary_max"],
            "contacts": data["contacts"],
            "description": (message.text or "").strip(),
            "status": "pending",
        }


        if referred_by is not None:
            payload["referred_by"] = referred_by

        vacancy = await repo.create_vacancy(payload)

        await repo.increment_vacancies_this_month(
            message.from_user.id
        )

        await repo.set_user_active_role(
            message.from_user.id,
            "employer"
        )

        await state.clear()

        await message.answer(
            "✅ Вакансия отправлена на модерацию. "
            "После проверки я сообщу результат.",
            reply_markup=main_menu(
                user_role="employer"
            )
        )

        await bot.send_message(
            settings.admin_chat_id,
            "🆕 Новая вакансия на модерацию:\n\n"
            + vacancy_public_text(
                vacancy,
                settings.bot_username
            ),
            reply_markup=moderation_keyboard(
                vacancy["id"]
            ),
        )

    except Exception as e:
        logger.error(
            f"Error in vacancy_description: {e}"
        )

        await message.answer(
            "❌ Ошибка при создании вакансии. "
            "Попробуйте позже."
        )

@router.callback_query(F.data.startswith("moderate_approve:"))
async def approve_vacancy(callback: CallbackQuery, repo: SupabaseRepository, settings: Settings, bot: Bot) -> None:
    vacancy_id = int(callback.data.split(":", 1)[1])
    vacancy = await repo.get_vacancy(vacancy_id)
    if not vacancy:
        await callback.answer("❌ Вакансия не найдена", show_alert=True)
        return

    channel_message = await bot.send_message(
        settings.channel_id,
        vacancy_public_text(vacancy, settings.bot_username),
        reply_markup=channel_post_keyboard(vacancy_id, settings.bot_username)
    )
    
    vacancy = await repo.approve_vacancy(vacancy_id, channel_message.message_id)

    post_url = (
        f"https://t.me/lisakovsk_job/"
        f"{channel_message.message_id}"
    )

    await bot.send_message(
        vacancy["employer_id"],
        "✅ Ваша вакансия одобрена и опубликована в канале. Хотите ускорить поиск?",
        reply_markup=vacancy_paid_features_keyboard(
            vacancy_id,
            post_url
        )
    )

    seekers = await repo.find_matching_seekers(vacancy)
    sent = await send_vacancy_notifications(repo=repo, bot=bot, settings=settings, vacancy=vacancy, seekers=seekers)

    await callback.message.edit_text(f"✅ Вакансия #{vacancy_id} одобрена. Уведомлений отправлено: {sent}.")
    await callback.answer()


@router.callback_query(F.data.startswith("moderate_reject:"))
async def reject_vacancy(callback: CallbackQuery, state: FSMContext) -> None:
    vacancy_id = int(callback.data.split(":", 1)[1])
    await state.set_state(RejectVacancyForm.reason)
    await state.update_data(reject_vacancy_id=vacancy_id, moderation_message_id=callback.message.message_id)
    await callback.message.answer(
        f"📝 Напишите причину отклонения вакансии #{vacancy_id} одним сообщением.",
        reply_markup=ForceReply(selective=True),
    )
    await callback.answer()


@router.message(RejectVacancyForm.reason)
async def reject_vacancy_reason(message: Message, state: FSMContext, repo: SupabaseRepository, bot: Bot) -> None:
    data = await state.get_data()
    vacancy_id = int(data["reject_vacancy_id"])
    reason = (message.text or "Не прошла модерацию").strip()
    vacancy = await repo.reject_vacancy(vacancy_id, reason)
    await bot.send_message(vacancy["employer_id"], f"❌ Вакансия отклонена модератором.\n\nПричина: {reason}")
    await message.answer(f"❌ Вакансия #{vacancy_id} отклонена. Причина отправлена работодателю.")
    await state.clear()


@router.callback_query(F.data.startswith("vacancy_like:"))
async def vacancy_like(callback: CallbackQuery, repo: SupabaseRepository, bot: Bot) -> None:
    vacancy_id = int(callback.data.split(":", 1)[1])
    logger.warning(
        f"LIKE CLICK | "
        f"user={callback.from_user.id} | "
        f"vacancy={vacancy_id}"
    )
    vacancy = await repo.get_vacancy(vacancy_id)
    seeker = await repo.get_seeker(callback.from_user.id)

    if not vacancy or not seeker:
        await callback.answer(
            "❌ Сначала заполните анкету соискателя.",
            show_alert=True
        )
        return
    
    if await repo.has_reacted(
        vacancy_id,
        callback.from_user.id
    ):
        await callback.answer(
            "✅ Вы уже откликнулись на эту вакансию.",
            show_alert=True
        )
        return


    await repo.set_reaction(
        vacancy_id,
        callback.from_user.id,
        "like"
    )

    await repo.set_reaction(vacancy_id, callback.from_user.id, "like")
    contact = f"@{callback.from_user.username}" if callback.from_user.username else f"telegram id {callback.from_user.id}"
    await bot.send_message(
        vacancy["employer_id"],
        f"📩 На вашу вакансию откликнулся соискатель:\n\n"
        f"{seeker_card(seeker)}\n\n📞 Контакты: {contact}",
    )

    await callback.message.edit_reply_markup(
        reply_markup=vacancy_responded_keyboard(
            vacancy_id
    )
)

    await callback.answer("✅ Отклик отправлен работодателю!", show_alert=True)

@router.callback_query(
    F.data.startswith("vacancy_already:")
)
async def vacancy_already(
    callback: CallbackQuery
) -> None:

    await callback.answer(
        "✅ Вы уже откликнулись на эту вакансию.",
        show_alert=True
    )


@router.callback_query(F.data.startswith("vacancy_dislike:"))
async def vacancy_dislike(callback: CallbackQuery, repo: SupabaseRepository) -> None:
    vacancy_id = int(callback.data.split(":", 1)[1])
    await repo.set_reaction(vacancy_id, callback.from_user.id, "dislike")
    await callback.message.delete()
    await callback.answer("🙈 Вакансия скрыта")


@router.callback_query(F.data.startswith("vacancy_complain:"))
async def vacancy_complain(callback: CallbackQuery, repo: SupabaseRepository, settings: Settings, bot: Bot) -> None:
    vacancy_id = int(callback.data.split(":", 1)[1])
    await repo.set_reaction(vacancy_id, callback.from_user.id, "complaint")
    await bot.send_message(settings.admin_chat_id, f"⚠️ Жалоба на вакансию #{vacancy_id} от пользователя {callback.from_user.id}")
    await callback.answer("⚠️ Жалоба отправлена модератору.", show_alert=True)


@router.callback_query(F.data.startswith("buy:"))
async def buy_feature(callback: CallbackQuery, repo: SupabaseRepository, settings: Settings, bot: Bot) -> None:
    _, feature, *rest = callback.data.split(":")
    vacancy_id = int(rest[0]) if rest else None
    
    try:
        referrals = await repo.count_referrals(callback.from_user.id)
        
        if feature == FEATURE_URGENT_BROADCAST:
            usage = await repo.get_or_create_usage(callback.from_user.id)
            if has_free_monthly_urgent(referrals, int(usage.get("urgent_broadcasts_this_month") or 0)):
                result = await fulfill_paid_feature(
                    repo=repo,
                    bot=bot,
                    settings=settings,
                    user_id=callback.from_user.id,
                    feature=feature,
                    vacancy_id=vacancy_id,
                )
                await callback.message.answer("🎁 Использован реферальный бонус: " + result)
                await callback.answer()
                return
                
        if feature == FEATURE_VIP_SEEKER and has_free_vip_bonus(referrals):
            if await repo.referral_vip_bonus_available(callback.from_user.id, referrals):
                await repo.activate_vip(callback.from_user.id)
                await repo.mark_referral_vip_bonus_used(callback.from_user.id)
                await callback.message.answer("🎁 Использован реферальный бонус: VIP-статус активирован на месяц.")
                await callback.answer()
                return
        
        # Для закрепа нужен выбор количества дней
        if feature == FEATURE_PIN_VACANCY and vacancy_id:
            from job_lisakovsk_bot.handlers.job import PinDaysForm
            await callback.message.answer("📌 Выберите количество дней (минимум 3):")
            return
        
        await manual_payment_start(callback, repo, settings)
        
    except Exception as e:
        logger.error(f"Error in buy_feature: {e}")
        await callback.answer("❌ Ошибка. Попробуйте позже.", show_alert=True)

@router.callback_query(F.data.startswith("manual:"))
async def manual_payment_start(callback: CallbackQuery, repo: SupabaseRepository, settings: Settings) -> None:
    _, feature, *rest = callback.data.split(":")
    vacancy_id = int(rest[0]) if rest else None
    
    # Получаем цену из БД
    if feature == "unlimited_vacancies":
        price = await repo.get_price("unlimited")
    elif feature == "vip_seeker":
        price = await repo.get_price("vip")
    elif feature == "pin_vacancy":
        price = await repo.get_price("pin")
    elif feature == "urgent_broadcast":
        price = await repo.get_price("broadcast")
    else:
        price = None
    
    if not price:
        await callback.message.answer("❌ Цена для этой услуги не настроена.")
        await callback.answer()
        return
    
    # Получаем номер телефона из БД
    phone = await repo.get_setting("beeline_payment_phone")
    if not phone:
        await callback.message.answer("❌ Номер телефона для оплаты не настроен.")
        await callback.answer()
        return
    
    # Название услуги
    if feature == "unlimited_vacancies":
        title = "Безлимит вакансий на месяц"
    elif feature == "vip_seeker":
        title = "VIP соискателя на месяц"
    elif feature == "pin_vacancy":
        title = "Закреп вакансии в канале"
    elif feature == "urgent_broadcast":
        title = "Срочная рассылка всем соискателям"
    else:
        title = "Услуга"
    
    payment = await repo.create_payment(
        user_id=callback.from_user.id,
        payment_type=PAYMENT_TYPE_MANUAL,
        amount=price,
        feature=feature,
        vacancy_id=vacancy_id,
    )
    
    await callback.message.answer(
        f"💳 Оплата функции\n\n"
        f"┌─────────────────────┐\n"
        f"│ 📦 {title}\n"
        f"│ 💰 Сумма: {price} ₸\n"
        f"└─────────────────────┘\n\n"
        f"📱 Переведите {price} ₸ на номер Билайн:\n"
        f"{phone}\n\n"
        f"📲 Как оплатить:\n"
        f"1. Откройте приложение банка\n"
        f"2. Выберите «Платежи» → «Мобильная связь»\n"
        f"3. Введите номер: {phone}\n"
        f"4. Укажите сумму: {price} ₸\n"
        f"5. Подтвердите платеж\n"
        f"6. Сохраните чек или сделайте скриншот\n\n"
        f"✅ После оплаты нажмите кнопку «Я оплатил» и пришлите чек",
        reply_markup=manual_payment_keyboard(payment["id"])
    )
    await callback.answer()



@router.callback_query(F.data.startswith("manual_paid:"))
async def manual_payment_paid(callback: CallbackQuery, state: FSMContext, repo: SupabaseRepository, settings: Settings, bot: Bot):
    payment_id = int(callback.data.split(":", 1)[1])
    payment = await repo.get_payment(payment_id)
    current_data = await state.get_data()

    await state.update_data(
    pending_payment_id=payment_id,
    pending_vacancy_data=current_data
)
    
    await state.set_state(
    VacancyForm.waiting_payment_check
)


    if not payment:
        await callback.answer("❌ Платёж не найден", show_alert=True)
        return
    
    await callback.message.answer(
        "📸 *Пришлите чек об оплате*\n\n"
        "Сделайте скриншот или фото квитанции и отправьте в этот чат.\n\n"
        "После проверки администратор подтвердит оплату.",
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("manual:pin_vacancy:"))
async def pin_vacancy_start(callback: CallbackQuery, state: FSMContext, repo: SupabaseRepository):
    vacancy_id = int(callback.data.split(":")[2])
    await state.update_data(pin_vacancy_id=vacancy_id)
    await state.set_state(PinDaysForm.waiting_for_days)
    await callback.message.answer(
        f"📌 *Закреп вакансии*\n\n"
        f"Укажите количество дней (минимум 3):\n\n"
        f"💰 Цена за день: {await repo.get_price('pin')} ₸\n"
        f"💳 Итого: {await repo.get_price('pin')} × <дни> = *{await repo.get_price('pin')} × N ₸*",
        parse_mode="Markdown"
    )
    await callback.answer()


@router.message(PinDaysForm.waiting_for_days)
async def pin_vacancy_days(message: Message, state: FSMContext, repo: SupabaseRepository, settings: Settings, bot: Bot):
    try:
        days = int(message.text.strip())
        if days < 3:
            await message.answer("❌ Минимальное количество дней — 3. Укажите число 3 или больше:")
            return
        
        data = await state.get_data()
        vacancy_id = data.get("pin_vacancy_id")
        price_per_day = await repo.get_price("pin")
        if not price_per_day:
            await message.answer("❌ Цена закрепления не настроена. Обратитесь к администратору.")
            await state.clear()
            return
        
        total_price = price_per_day * days
        
        payment = await repo.create_payment(
            user_id=message.from_user.id,
            payment_type=PAYMENT_TYPE_MANUAL,
            amount=total_price,
            feature="pin_vacancy",
            vacancy_id=vacancy_id,
        )
        
        await state.update_data(pin_days=days)
        
        phone = await repo.get_setting("beeline_payment_phone")
        if not phone:
            await message.answer("❌ Номер телефона для оплаты не настроен. Обратитесь к администратору.")
            await state.clear()
            return
        
        await message.answer(
            f"💳 *Оплата закрепления вакансии*\n\n"
            f"┌─────────────────────┐\n"
            f"│ 📌 Закреп в канале\n"
            f"│ 📅 Количество дней: {days}\n"
            f"│ 💰 Цена за день: {price_per_day} ₸\n"
            f"│ 💳 Итого: *{total_price} ₸*\n"
            f"└─────────────────────┘\n\n"
            f"📱 *Переведите {total_price} ₸ на номер Билайн:*\n"
            f"`{phone}`\n\n"
            f"✅ *После оплаты* нажмите кнопку «Я оплатил» и пришлите чек",
            reply_markup=manual_payment_keyboard(payment["id"]),
            parse_mode="Markdown"
        )
        await state.clear()
        
    except ValueError:
        await message.answer("❌ Ошибка: нужно ввести число. Укажите количество дней (3 или больше):")


@router.message(
    VacancyForm.waiting_payment_check,
    F.photo
)
async def handle_payment_check(
    message: Message,
    state: FSMContext,
    repo: SupabaseRepository,
    settings: Settings,
    bot: Bot
):
    data = await state.get_data()
    payment_id = data.get("pending_payment_id")

    if not payment_id:
        return

    payment = await repo.get_payment(payment_id)

    if not payment:
        await message.answer(
            "❌ Платёж не найден. Попробуйте снова."
        )
        return

    feature_names = {
        "unlimited_vacancies": "Безлимит вакансий",
        "vip_seeker": "VIP соискатель",
        "pin_vacancy": "Закреп вакансии",
        "urgent_broadcast": "Срочная рассылка",
    }

    caption = (
        f"🧾 Новый чек на подтверждение\n\n"
        f"💰 Сумма: {payment['amount']} ₸\n"
        f"📦 Услуга: {feature_names.get(payment['feature'], payment['feature'])}\n"
        f"👤 Пользователь: {payment['user_id']}\n"
        f"🆔 ID заявки #{payment_id}"
    )

    await bot.send_photo(
        settings.admin_chat_id,
        message.photo[-1].file_id,
        caption=caption,
        reply_markup=admin_manual_payment_keyboard(payment_id)
    )

    await state.update_data(
        pending_payment_id=None
    )

    await message.answer(
        "✅ Чек отправлен администратору на проверку.\n\n"
        "После подтверждения оплаты публикация вакансии продолжится автоматически."
    )

@router.callback_query(F.data.startswith("manual_confirm:"))
async def manual_payment_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    repo: SupabaseRepository,
    settings: Settings,
    bot: Bot
) -> None:

    payment_id = int(callback.data.split(":", 1)[1])

    payment = await repo.mark_payment_paid(payment_id)

    if not payment:
        await callback.answer(
            "❌ Платёж не найден",
            show_alert=True
        )
        return

    result = await fulfill_paid_feature(
        repo=repo,
        bot=bot,
        settings=settings,
        user_id=payment["user_id"],
        feature=payment["feature"],
        vacancy_id=payment.get("vacancy_id"),
    )


    if payment["feature"] == "unlimited_vacancies":

        user_key = StorageKey(
            bot_id=bot.id,
            chat_id=payment["user_id"],
            user_id=payment["user_id"]
        )

        user_state = await state.storage.get_data(
            key=user_key
        )

        pending_data = user_state.get(
            "pending_vacancy_data"
        )

        if pending_data:

            await state.storage.set_data(
                key=user_key,
                data=pending_data
            )

            await state.storage.set_state(
                key=user_key,
                state=VacancyForm.description
            )

            await bot.send_message(
                payment["user_id"],
                "✅ Безлимит активирован!\n\n"
                "Теперь отправьте описание вакансии ещё раз."
            )

    await callback.message.answer(
        f"✅ Ручная оплата #{payment_id} подтверждена.\n{result}"
    )

    await callback.answer()

@router.callback_query(F.data.startswith("manual_reject:"))
async def manual_payment_reject(callback: CallbackQuery, repo: SupabaseRepository, bot: Bot) -> None:
    payment_id = int(callback.data.split(":", 1)[1])
    payment = await repo.reject_payment(payment_id)
    if payment:
        await bot.send_message(payment["user_id"], "❌ Ручная оплата отклонена администратором.")
    await callback.message.edit_text(f"❌ Ручная оплата #{payment_id} отклонена.")
    await callback.answer()


@router.message(
    F.text.in_(
        {
            "👥 Пригласить друга",
            "📣 Поделиться проектом"
        }
    )
)
@router.message(Command("invite"))
async def invite_friend(
    message: Message,
    repo: SupabaseRepository,
    settings: Settings
) -> None:

    referrals_count = await repo.count_referrals(
        message.from_user.id
    )

    link = referral_deep_link(
        settings.bot_username,
        message.from_user.id
    )

    await message.answer(
        f"🔗 Ваша ссылка для приглашения:\n"
        f"`{link}`\n\n"

        f"👥 Приглашено друзей: {referrals_count}\n\n"

        f"{referral_bonus_text(referrals_count)}",

        parse_mode="Markdown"
    )

@router.message(
    F.text.in_(
        {
            "🔍 Смотреть вакансии",
            "📺 Лента вакансий"
        }
    )
)
async def our_channel(
    message: Message,
    settings: Settings
):
    await message.answer(
        "📢 *Лента вакансий Лисаковска*\n\n"
        "Все новые вакансии публикуются в нашем канале.\n\n"
        "Нажмите кнопку ниже 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📱 Открыть ленту вакансий",
                        url="https://t.me/lisakovsk_job"
                    )
                ]
            ]
        )
    )

@router.message(F.text == "📝 Заполнить анкету")
async def find_job_button(message: Message, state: FSMContext):
    await seeker_start(message, state)


@router.message(F.text == "Наши проекты")
async def projects(message: Message, settings: Settings) -> None:
    await message.answer(
        "🌟 Наши проекты:\n\n"
        f"🔮 Оракул: {settings.project_oracle_url}\n"
        f"⭐ Рейтинг: {settings.project_rating_url}\n"
        f"🛠 Мастерская: {settings.project_workshop_url}"
    )


@router.message(Command("lk"))
async def lk_command(message: Message, repo: SupabaseRepository):
    await my_stats(message, repo)


@router.message(F.text.in_({"👤 Личный кабинет", "/my_stats"}))
async def my_stats(
    message: Message,
    repo: SupabaseRepository
) -> None:

    try:

        user_role = await get_user_role(
            message.from_user.id,
            repo
        )

        role_display = (
            "Работодатель"
            if user_role == "employer"
            else "Соискатель"
            if user_role == "seeker"
            else "Не определена"
        )

        # =========================
        # РАБОТОДАТЕЛЬ
        # =========================

        if user_role == "employer":

            try:

                stats = await repo.employer_stats(
                    message.from_user.id
                )

                text = (
                    f"📊 Статистика работодателя\n\n"

                    f"👤 Режим: {role_display}\n\n"

                    f"📌 Всего вакансий: "
                    f"{stats.get('vacancies_total', 0)}\n"

                    f"✅ Активные: "
                    f"{stats.get('active_vacancies', 0)}\n"

                    f"⏳ На модерации: "
                    f"{stats.get('pending_vacancies', 0)}\n"

                    f"🔒 Закрытые: "
                    f"{stats.get('closed_vacancies', 0)}\n"

                    f"❌ Отклонённые: "
                    f"{stats.get('rejected_vacancies', 0)}\n\n"

                    f"👁️ Просмотров: "
                    f"{stats.get('views', 0)}\n"

                    f"📩 Откликов: "
                    f"{stats.get('responses', 0)}"
                )

                await message.answer(
    text,
    reply_markup=employer_cabinet_keyboard()
)

            except Exception as e:

                logger.error(
                    f"Employer stats error: {e}"
                )

                await message.answer(
    "⚠️ Статистика работодателя временно недоступна.\n\n"
    "Но ваши вакансии продолжают работать 🙂",
    reply_markup=employer_cabinet_keyboard()
)

            return

        # =========================
        # СОИСКАТЕЛЬ
        # =========================

        seeker = await repo.get_seeker(
            message.from_user.id
        )

        if not seeker:

            await message.answer(
                "📝 У вас пока нет анкеты соискателя.\n\n"
                "Нажмите кнопку "
                "«📝 Заполнить анкету» "
                "в меню ниже 👇"
            )

            return

        try:

            stats = await repo.seeker_stats(
                message.from_user.id
            )

            text = (
                f"📊 Статистика соискателя\n\n"

                f"👤 Режим: {role_display}\n\n"

                f"👁️ Просмотров: "
                f"{stats.get('views', 0)}\n"

                f"📩 Откликов: "
                f"{stats.get('responses', 0)}"
            )

            await message.answer(
    text,
    reply_markup=seeker_cabinet_keyboard()
)

        except Exception as e:

            logger.error(
                f"Seeker stats error: {e}"
            )

            await message.answer(
                "⚠️ Статистика соискателя временно недоступна."
            )

    except Exception as e:

        logger.error(
            f"My stats error: {e}"
        )

        await message.answer(
            "❌ Ошибка загрузки кабинета."
        )


@router.message(F.text == "📝 Моя анкета")
async def my_resume(
    message: Message,
    repo: SupabaseRepository
) -> None:

    seeker = await repo.get_seeker(
        message.from_user.id
    )

    if not seeker:

        await message.answer(
            "❌ Анкета пока не заполнена."
        )

        return

    await message.answer(
    text,
    reply_markup=seeker_resume_keyboard()
)


@router.message(F.text == "📨 Отклики")
async def employer_responses(
    message: Message,
    repo: SupabaseRepository
):

    try:

        vacancies = await repo.list_employer_vacancies(
            message.from_user.id
        )

        if not vacancies:

            await message.answer(
                "📭 У вас пока нет вакансий."
            )

            return

        text = "📨 Отклики на вакансии:\n\n"

        for vacancy in vacancies[:10]:

            responses = await repo.list_vacancy_responses(
                vacancy["id"]
            )

            if not responses:
                continue

            status = vacancy.get("status")

            status_text = {
                "approved": "✅ Активна",
                "pending": "⏳ На модерации",
                "rejected": "❌ Отклонена",
                "closed": "🔒 Закрыта",
            }.get(status, status)

            text += (
                f"💼 {vacancy.get('title', 'Без названия')}\n"
                f"{status_text}\n"
                f"📩 Откликов: {len(responses)}\n\n"
            )

        await message.answer(
                (
                    f"💼 {vacancy.get('title', 'Без названия')}\n"
                    f"{status_text}\n"
                    f"📩 Откликов: {len(responses)}"
                ),
                reply_markup=employer_candidates_keyboard(
                    vacancy["id"]
                )
            )

    except Exception as e:

        logger.error(
            f"Employer responses error: {e}"
        )

        await message.answer(
            "❌ Ошибка загрузки откликов."
        )


@router.callback_query(F.data.startswith("view_candidates:"))
async def view_candidates(
    callback: CallbackQuery,
    repo: SupabaseRepository
):

    vacancy_id = int(
        callback.data.split(":")[1]
    )

    responses = await repo.list_vacancy_responses(
        vacancy_id
    )

    if not responses:

        await callback.message.answer(
            "📭 Пока никто не откликнулся."
        )

        return

    text = "👥 Кандидаты:\n\n"

    for response in responses[:10]:

        seeker = await repo.get_seeker(
            response["seeker_id"]
        )

        if not seeker:
            continue

        logger.warning(
            f"SEEKER DATA: {seeker}"
        )

        logger.warning(
            f"SEEKER DATA: {seeker}"
        )

        username = seeker.get("username")

        if username:
            username = f"@{username}"
        else:
            username = "не указан"

        salary = format_salary(
            seeker.get("salary_min"),
            seeker.get("salary_max")
        )

        contacts = seeker.get(
            "contacts",
            "не указаны"
        )

        text += (
            f"👤 {seeker.get('full_name', 'Без имени')}\n"
            f"💰 {salary}\n"
            f"📞 {contacts}\n\n"
        )

    await callback.message.answer(text)

    await callback.answer()

@router.message(Command("admin_stats"))
async def admin_stats(message: Message, repo: SupabaseRepository, settings: Settings) -> None:
    if message.chat.id != settings.admin_chat_id:
        await message.answer("⛔ Команда доступна только в админ-чате.")
        return
    await message.answer(admin_stats_text(await repo.admin_stats()))

@router.message(F.text == "⬅️ Назад")
async def back_to_main_menu(
    message: Message,
    repo: SupabaseRepository
) -> None:

    user_role = await get_user_role(
        message.from_user.id,
        repo
    )

    await message.answer(
        "🏠 Главное меню",
        reply_markup=main_menu(
            user_role=user_role
        )
    )

@router.message(F.text == "📊 Админ-статистика")
async def admin_stats_button(
    message: Message,
    repo: SupabaseRepository,
    settings: Settings,
) -> None:

    if message.chat.id != settings.admin_chat_id:
        return

    await message.answer(
        admin_stats_text(
            await repo.admin_stats()
        )
    )


@router.callback_query(F.data.startswith("hide_post:"))
async def hide_post(callback: CallbackQuery) -> None:
    await callback.message.delete()
    await callback.answer("🙈 Пост скрыт", show_alert=False)


@router.message(Command("menu"))
async def back_to_menu(message: Message, repo: SupabaseRepository):
    user_role = await get_user_role(message.from_user.id, repo)
    await message.answer("📋 Главное меню:", reply_markup=main_menu(user_role))


@router.callback_query(F.data == "found_work")
async def found_work(callback: CallbackQuery, repo: SupabaseRepository) -> None:
    await repo.mark_seeker_found_work(callback.from_user.id)
    await callback.answer("🎉 Поздравляю! Анкета отмечена как закрытая.", show_alert=True)


@router.callback_query(F.data.startswith("close_vacancy:"))
async def close_vacancy(callback: CallbackQuery, repo: SupabaseRepository) -> None:
    vacancy_id = int(callback.data.split(":", 1)[1])
    vacancy = await repo.close_vacancy(vacancy_id, callback.from_user.id)
    if not vacancy:
        await callback.answer("❌ Вакансия не найдена", show_alert=True)
        return
    await callback.answer("✅ Вакансия отмечена как закрытая.", show_alert=True)


@router.callback_query(F.data.startswith("hide_post:"))
async def hide_post(callback: CallbackQuery) -> None:
    await callback.message.delete()
    await callback.answer("🙈 Пост скрыт", show_alert=False)




@router.message(Command("set_limit"))
async def set_free_limit(message: Message, repo: SupabaseRepository, settings: Settings):
    if message.chat.id != settings.admin_chat_id:
        await message.answer("⛔ Доступно только админам")
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("📝 Использование: /set_limit <число>\nПример: /set_limit 5")
        return
    
    try:
        limit = int(args[1])
        await repo.set_setting("free_vacancy_limit", str(limit))
        await message.answer(f"✅ Бесплатный лимит вакансий установлен: {limit} в месяц")
    except ValueError:
        await message.answer("❌ Нужно число")


@router.message(Command("enable_free"))
async def enable_free_vacancies(message: Message, repo: SupabaseRepository, settings: Settings):
    if message.chat.id != settings.admin_chat_id:
        await message.answer("⛔ Доступно только админам")
        return
    
    await repo.set_setting("free_vacancy_enabled", "true")
    await message.answer("✅ Бесплатные вакансии ВКЛЮЧЕНЫ")


@router.message(Command("disable_free"))
async def disable_free_vacancies(message: Message, repo: SupabaseRepository, settings: Settings):
    if message.chat.id != settings.admin_chat_id:
        await message.answer("⛔ Доступно только админам")
        return
    
    await repo.set_setting("free_vacancy_enabled", "false")
    await message.answer("✅ Бесплатные вакансии ОТКЛЮЧЕНЫ. Только платные.")


@router.message(Command("set_price"))
async def set_price(message: Message, repo: SupabaseRepository, settings: Settings):
    if message.chat.id != settings.admin_chat_id:
        await message.answer("⛔ Доступно только админам")
        return
    
    args = message.text.split()
    if len(args) != 3:
        await message.answer("📝 Использование: /set_price <услуга> <цена>\n\nУслуги: unlimited, pin, broadcast, vip\nПример: /set_price unlimited 500")
        return
    
    service = args[1]
    try:
        price = int(args[2])
    except ValueError:
        await message.answer("❌ Цена должна быть числом")
        return
    
    if service == "unlimited":
        await repo.set_setting("price_unlimited", str(price))
    elif service == "pin":
        await repo.set_setting("price_pin_per_day", str(price))
    elif service == "broadcast":
        await repo.set_setting("price_broadcast", str(price))
    elif service == "vip":
        await repo.set_setting("price_vip", str(price))
    else:
        await message.answer("❌ Неизвестная услуга. Доступные: unlimited, pin, broadcast, vip")
        return
    
    await message.answer(f"✅ Цена для {service} установлена: {price} ₸")


@router.message(Command("set_price_unlimited"))
async def set_price_unlimited_start(message: Message, state: FSMContext, repo: SupabaseRepository, settings: Settings):
    if message.chat.id != settings.admin_chat_id:
        await message.answer("⛔ Доступно только админам")
        return
    
    current = await repo.get_setting("price_unlimited")
    if not current:
        current = "не настроено"
    
    await state.update_data(setting_key="price_unlimited")
    await state.set_state(AdminSettingsForm.waiting_for_price)
    await message.answer(f"💰 Текущая цена безлимита: {current} ₸\n\nВведите новую цену (только число):")


@router.message(Command("set_price_vip"))
async def set_price_vip_start(message: Message, state: FSMContext, repo: SupabaseRepository, settings: Settings):
    if message.chat.id != settings.admin_chat_id:
        await message.answer("⛔ Доступно только админам")
        return
    
    current = await repo.get_setting("price_vip")
    if not current:
        current = "не настроено"
    
    await state.update_data(setting_key="price_vip")
    await state.set_state(AdminSettingsForm.waiting_for_price)
    await message.answer(f"💰 Текущая цена VIP: {current} ₸\n\nВведите новую цену (только число):")

@router.message(Command("set_price_pin"))
async def set_price_pin_start(message: Message, state: FSMContext, repo: SupabaseRepository, settings: Settings):
    #if message.chat.id != settings.admin_chat_id:
        #await message.answer("⛔ Доступно только админам")
        #return
    
    current = await repo.get_setting("price_pin_per_day")
    if not current:
        current = "не настроено"
    
    await state.update_data(setting_key="price_pin_per_day")
    await state.set_state(AdminSettingsForm.waiting_for_price)
    await message.answer(f"💰 Текущая цена закрепления (за день): {current} ₸\n\nВведите новую цену (только число):")

@router.message(Command("set_price_broadcast"))
async def set_price_broadcast_start(message: Message, state: FSMContext, repo: SupabaseRepository, settings: Settings):
    if message.chat.id != settings.admin_chat_id:
        await message.answer("⛔ Доступно только админам")
        return
    
    current = await repo.get_setting("price_broadcast")
    if not current:
        current = "не настроено"
    
    await state.update_data(setting_key="price_broadcast")
    await state.set_state(AdminSettingsForm.waiting_for_price)
    await message.answer(f"💰 Текущая цена рассылки: {current} ₸\n\nВведите новую цену (только число):")

@router.message(AdminSettingsForm.waiting_for_price)
async def save_price(message: Message, state: FSMContext, repo: SupabaseRepository, settings: Settings):
    if message.chat.id != settings.admin_chat_id:
        await state.clear()
        return
    
    try:
        price = int(message.text.strip())
        data = await state.get_data()
        key = data.get("setting_key")
        
        if key:
            await repo.set_setting(key, str(price))
            await message.answer(f"✅ Цена для {key} установлена: {price} ₸")
        else:
            await message.answer("❌ Ошибка: неизвестный параметр")
    except ValueError:
        await message.answer("❌ Ошибка: нужно ввести число\n\nПопробуйте ещё раз:")
        return
    
    await state.clear()

@router.message(Command("set_phone"))
async def set_phone_start(message: Message, state: FSMContext, repo: SupabaseRepository, settings: Settings):
    if message.chat.id != settings.admin_chat_id:
        await message.answer("⛔ Доступно только админам")
        return
    
    current = await repo.get_setting("beeline_payment_phone")
    if not current:
        current = "не настроен"
    
    await state.set_state(AdminSettingsForm.waiting_for_phone)
    await message.answer(f"📱 Текущий номер Билайн: {current}\n\nВведите новый номер в формате +77051234567:")


@router.message(AdminSettingsForm.waiting_for_phone)
async def save_phone(message: Message, state: FSMContext, repo: SupabaseRepository, settings: Settings):
    if message.chat.id != settings.admin_chat_id:
        await state.clear()
        return
    
    phone = message.text.strip()
    await repo.set_setting("beeline_payment_phone", phone)
    await message.answer(f"✅ Номер Билайн изменён: {phone}")
    await state.clear()

@router.message(Command("show_settings"))
async def show_settings(message: Message, repo: SupabaseRepository, settings: Settings):
    if message.chat.id != settings.admin_chat_id:
        await message.answer("⛔ Доступно только админам")
        return
    
    unlimited = await repo.get_setting("price_unlimited") or "❌ не настроено"
    vip = await repo.get_setting("price_vip") or "❌ не настроено"
    pin = await repo.get_setting("price_pin_per_day") or "❌ не настроено"
    broadcast = await repo.get_setting("price_broadcast") or "❌ не настроено"
    phone = await repo.get_setting("beeline_payment_phone") or "❌ не настроен"
    free_limit = await repo.get_setting("free_vacancy_limit") or "❌ не настроен"
    free_enabled = await repo.get_setting("free_vacancy_enabled") or "true"
    
    
    await message.answer(
        f"📊 *Текущие настройки бота*\n\n"
        f"💰 Безлимит: {unlimited} ₸\n"
        f"💰 VIP: {vip} ₸\n"
        f"💰 Закреп (за день): {pin} ₸\n"
        f"💰 Рассылка: {broadcast} ₸\n"
        f"📱 Номер Билайн: `{phone}`\n"
        f"📊 Лимит вакансий: {free_limit}\n"
        f"🟢 Бесплатные вакансии: {'ВКЛ' if free_enabled == 'true' else 'ВЫКЛ'}\n\n"
        f"✏️ *Команды для изменения:*\n"
        f"/set_price_unlimited\n"
        f"/set_price_vip\n"
        f"/set_price_pin\n"
        f"/set_price_broadcast\n"
        f"/set_phone\n"
        f"/set_limit\n"
        f"/enable_free /disable_free",
        parse_mode="Markdown"
    )

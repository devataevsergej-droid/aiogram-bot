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
    edit_vacancy_keyboard,
    candidate_preview_keyboard,
    employer_vacancy_keyboard,
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
    continue_keyboard,
    spheres_keyboard,
    company_start_keyboard,
    vacancies_keyboard,
    vacancy_responded_keyboard,
    vacancy_paid_features_keyboard,
    skip_keyboard,
    city_keyboard,
    contacts_keyboard,
    company_keyboard,
    confirm_vacancy_edit_keyboard,
    confirm_contacts_edit_keyboard,
    confirm_salary_edit_keyboard,
    confirm_schedule_edit_keyboard,
    confirm_title_edit_keyboard,
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
async def toggle_role(
    message: Message,
    state: FSMContext,
    repo: SupabaseRepository
):

    await state.clear()

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

    location = State()

    requirements = State()
    benefits = State()

    contacts = State()
    description = State()

    waiting_payment_check = State()


class EditVacancyForm(StatesGroup):
    waiting_title = State()
    waiting_salary = State()
    waiting_schedule = State()
    waiting_description = State()
    waiting_contacts = State()
    
    confirm_contacts = State()
    confirm_title = State()
    confirm_salary = State()
    confirm_schedule = State()
    confirm_description = State()


class CompanyForm(StatesGroup):
    intro = State()

    name = State()

    industry = State()
    hiring_keywords = State()

    city = State()
    contacts = State()
    description = State()

class CompanyEditForm(StatesGroup):
    city = State()
    contacts = State()
    description = State()    

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

    referrer_id = parse_referral_arg(
        command.args
    )

    arg = command.args

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

        await state.clear()

        await state.set_state(
            VacancyForm.title
        )

        await message.answer(
            "👔 Кого ищете? Напишите должность или услугу.\n\n"
            "Например:\n"
            "Сварщик\n"
            "Бариста\n"
            "Продавец"
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
) -> None:

    await state.clear()

    await state.set_state(
        VacancyForm.title
    )

    await message.answer(
        "👔 Кого ищете? Напишите должность или услугу.\n\n"
        "Например:\n"
        "Сварщик\n"
        "Бариста\n"
        "Продавец"
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
        "Продолжить",
        reply_markup=continue_keyboard()
    )


@router.message(
    SeekerForm.intro,
    F.text == "✅ Продолжить"
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
        "💰 Укажите желаемую зарплату в тысячах тенге.\n\n"
        "Например:\n"
        "300\n"
        "400\n"
        "300-500\n\n"
        "Или нажмите:\n"
        "⏭ Пропустить",
        reply_markup=skip_keyboard()
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
    "Категория CE",
    reply_markup=skip_keyboard()
)

@router.message(SeekerForm.driver_license)
async def seeker_driver_license(
    message: Message,
    state: FSMContext
) -> None:

    value = (message.text or "").strip()

    if value.lower() in [
        "пропустить",
        "⏭ пропустить"
    ]:
        value = None

    await state.update_data(
        driver_license=value
    )

    await state.set_state(
        SeekerForm.city
    )

    await message.answer(
        "📍 В каком городе вы ищете работу?\n\n"
        "Введите название города вручную\n"
        "или выберите вариант ниже.",
        reply_markup=city_keyboard()
    )


@router.message(SeekerForm.city)
async def seeker_city(
    message: Message,
    state: FSMContext
) -> None:

    value = (message.text or "").strip()

    if value.lower() in [
        "пропустить",
        "⏭ пропустить"
    ]:
        value = None

    elif value == "🏠 Удалённо":
        value = "Удалённо"

    await state.update_data(
        city=value
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

    if text.lower() in [
        "пропустить",
        "⏭ пропустить"
    ]:

        await state.update_data(
            salary_min=None,
            salary_max=None
        )

    else:

        try:

            if "-" in text:

                salary_min, salary_max = (
                    text.replace(" ", "")
                    .split("-", 1)
                )

                await state.update_data(
                    salary_min=int(salary_min),
                    salary_max=int(salary_max)
                )

            else:

                salary = int(
                    text.replace(" ", "")
                )

                await state.update_data(
                    salary_min=salary,
                    salary_max=None
                )

        except ValueError:

            await message.answer(
                "❌ Укажите зарплату правильно.\n\n"
                "Например:\n"
                "300\n"
                "400\n"
                "300-500"
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
        "📞 Предпочтительный способ связи",
        reply_markup=contacts_keyboard()
    )

@router.message(SeekerForm.contacts)
async def seeker_contacts_finish(
    message: Message,
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    try:

        value = (message.text or "").strip()

        if value.lower() in [
            "пропустить",
            "⏭ пропустить"
        ]:
            value = None

        await state.update_data(
            contacts=value
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


@router.message(
    F.text == "✅ Создать карточку компании"
)
async def start_company_creation(
    message: Message,
    state: FSMContext
) -> None:

    await state.clear()

    await state.set_state(
        CompanyForm.intro
    )

    await message.answer(
        "<b>🏢 Карточка компании</b>\n\n"

        "Чем подробнее заполнена карточка, тем лучше система сможет:\n\n"

        "• рекомендовать вашу компанию кандидатам\n"
        "• подбирать подходящих сотрудников\n"
        "• улучшать качество откликов\n"
        "• использовать AI-подбор в будущем\n\n"

        "<b>Особенно важны:</b>\n"
        "🏢 Название компании\n"
        "📍 Город\n"
        "📝 Описание деятельности\n\n"

        "Нажмите:\n"
        "✅ Продолжить",

        parse_mode="HTML",
        reply_markup=continue_keyboard()
    )   

@router.message(CompanyForm.intro)
async def company_intro(
    message: Message,
    state: FSMContext
) -> None:

    await state.set_state(
        CompanyForm.name
    )

    await message.answer(
        "🏢 Введите название компании.\n\n"
        "Например:\n"
        "ТОО Лисаковск Хаб\n"
        "Магазин Уют\n"
        "ИП Иванов"
    )



@router.message(CompanyForm.name)
async def company_name(
    message: Message,
    state: FSMContext
) -> None:

    await state.update_data(
        name=(message.text or "").strip()
    )

    await state.set_state(
        CompanyForm.industry
    )

    await message.answer(
        "🏭 Укажите сферу деятельности компании.\n\n"
        "Например:\n"
        "Строительство\n"
        "Торговля\n"
        "Общепит\n"
        "Производство\n"
        "IT\n"
        "Услуги"
    )


@router.message(CompanyForm.industry)
async def company_industry(
    message: Message,
    state: FSMContext
) -> None:

    await state.update_data(
        industry=(message.text or "").strip()
    )

    await state.set_state(
        CompanyForm.hiring_keywords
    )

    await message.answer(
        "👥 Кого вы обычно ищете?\n\n"
        "Перечислите через запятую.\n\n"
        "Например:\n"
        "Сварщик, Монтажник, Водитель\n\n"
        "или\n\n"
        "Продавец, Кассир, Администратор"
    )


@router.message(CompanyForm.hiring_keywords)
async def company_hiring_keywords(
    message: Message,
    state: FSMContext
) -> None:

    await state.update_data(
        hiring_keywords=(message.text or "").strip()
    )

    await state.set_state(
        CompanyForm.city
    )

    await message.answer(
        "📍 Укажите город компании."
    )


@router.message(CompanyForm.city)
async def company_city(
    message: Message,
    state: FSMContext
) -> None:

    await state.update_data(
        city=(message.text or "").strip()
    )

    await state.set_state(
        CompanyForm.contacts
    )

    await message.answer(
        "📞 Укажите контакты компании.\n\n"
        "Например:\n"
        "+7 777 123 45 67\n"
        "@company\n"
        "WhatsApp"
    )


@router.message(CompanyForm.contacts)
async def company_contacts(
    message: Message,
    state: FSMContext
) -> None:

    await state.update_data(
        contacts=(message.text or "").strip()
    )

    await state.set_state(
        CompanyForm.description
    )

    await message.answer(
        "📝 Кратко расскажите о компании.\n\n"
        "Например:\n"
        "Розничная торговля товарами для дома.\n"
        "Работаем более 10 лет."
    )


@router.message(CompanyForm.description)
async def company_description(
    message: Message,
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    data = await state.get_data()

    payload = {
        "owner_id": message.from_user.id,
        "name": data.get("name"),

        "industry": data.get("industry"),
        "hiring_keywords": data.get("hiring_keywords"),

        "city": data.get("city"),
        "contacts": data.get("contacts"),
        "description": (message.text or "").strip(),

        "active": True,
    }

    await repo.create_company(payload)

    await state.clear()

    await message.answer(
        "✅ Компания успешно создана.\n\n"
        "Теперь вы сможете использовать её при публикации вакансий."
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
async def vacancy_title(
    message: Message,
    state: FSMContext
) -> None:

    text = (message.text or "").strip()

    if text in {
        "👤 Личный кабинет",
        "📋 Мои вакансии",
        "🏢 Моя компания",
        "⬅️ Назад",
    }:
        await state.clear()
        return

    await state.update_data(
        title=text
    )

    await state.set_state(
        VacancyForm.sphere
    )

    await message.answer(
        "📂 Выберите сферу:",
        reply_markup=spheres_keyboard(
            "vacancy_sphere"
        )
    )


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
        "💰 Укажите зарплату\n\n"

        "Примеры:\n"
        "2 = 2 тыс. тг.\n"
        "20 = 20 тыс. тг.\n"
        "200 = 200 тыс. тг.\n"
        "500 = 500 тыс. тг.\n"
        "1000 = 1 млн. тг.\n\n"

        "Диапазон:\n"
        "200-300 = 200–300 тыс. тг.\n"
        "1000-1500 = 1–1,5 млн. тг."
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

    await state.set_state(
        VacancyForm.location
    )

    await message.answer(
        "📍 Где находится работа?\n\n"

        "Примеры:\n"
        "Лисаковск\n"
        "Рудный\n"
        "Костанай\n"
        "Астана\n"
        "Удалённо\n"
        "Вахта"
    )



@router.message(VacancyForm.location)
async def vacancy_location(
    message: Message,
    state: FSMContext
) -> None:

    await state.update_data(
        location=(message.text or "").strip()
    )

    await state.set_state(
        VacancyForm.contacts
    )

    await message.answer(
        "📞 Как с вами связаться?\n\n"

        "Укажите телефон, e-mail, мессенджер и удобное время для связи.\n\n"

        "Например:\n"
        "87779996655\n"
        "izi.corp@mail.ru\n"
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
        "📝 Опишите обязанности и требования\n\n"

        "Пример:\n"
        "• Консультирование клиентов\n"
        "• Работа с кассой\n"
        "• Приём и выкладка товара\n"
        "• Ответственность\n"
        "• Умение работать в коллективе"
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
            "company_id": data.get("company_id"),

            "title": data["title"],
            "sphere": data["sphere"],
            "schedule": data["schedule"],
            "location": data["location"],

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
            parse_mode="HTML",
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
        vacancy_public_text(
            vacancy,
            settings.bot_username
        ),
        parse_mode="HTML",
        reply_markup=channel_post_keyboard(
            vacancy_id,
            settings.bot_username
        )
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
    state: FSMContext,
    repo: SupabaseRepository,
    settings: Settings
) -> None:

    await state.clear()

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
    state: FSMContext,
    settings: Settings
) -> None:

    await state.clear()

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
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    logger.warning("LK CLICKED")

    logger.warning(
        f"LK CURRENT STATE = {await state.get_state()}"
    )

    await state.clear()

    current_state = await state.get_state()

    logger.warning(
        f"LK AFTER CLEAR | state={current_state}"
    )

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


def show_value(value: str | None) -> str:

    if not value:
        return "Не указано"

    if value.lower() in {
        "пропустить",
        "⏭ пропустить",
        "➡️ пропустить",
        "⏩ пропустить",
    }:
        return "Не указано"

    return value


def format_phone(phone: str | None) -> str:

    if not phone:
        return "Не указано"

    digits = "".join(
        ch for ch in phone
        if ch.isdigit()
    )

    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]

    if len(digits) == 11 and digits.startswith("7"):
        return (
            f"+7 {digits[1:4]} "
            f"{digits[4:7]} "
            f"{digits[7:9]} "
            f"{digits[9:11]}"
        )

    return phone


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
    
    salary = format_salary(
        seeker.get("salary_min"),
        seeker.get("salary_max")
    )

    text = (
        f"<b>👤 Соискатель</b>\n"
        f"{show_value(seeker.get('full_name'))}\n\n"

        f"<b>🎂 Возраст</b>\n"
        f"{show_value(str(seeker.get('age')) if seeker.get('age') else None)}\n\n"

        f"<b>📱 Телефон</b>\n"
        f"{format_phone(seeker.get('phone'))}\n\n"

        f"<b>🎯 Желаемые должности</b>\n"
        f"{show_value(seeker.get('desired_positions'))}\n\n"

        f"<b>🏷 Ключевые навыки</b>\n"
        f"{show_value(seeker.get('skills'))}\n\n"

        f"<b>💰 Зарплата</b>\n"
        f"{salary}\n\n"

        f"<b>📍 Город</b>\n"
        f"{show_value(seeker.get('city'))}\n\n"

        f"<b>🕒 График</b>\n"
        f"{show_value(seeker.get('schedule'))}\n\n"

        f"<b>🚚 Вахта</b>\n"
        f"{show_value(seeker.get('rotation_work'))}\n\n"

        f"<b>🚘 Водительское удостоверение</b>\n"
        f"{show_value(seeker.get('driver_license'))}\n\n"

        f"<b>📝 О себе</b>\n"
        f"{show_value(seeker.get('about'))}\n\n"

        f"<b>📞 Способ связи</b>\n"
        f"{show_value(seeker.get('contacts'))}"
    )

    await message.answer(
        text,
        parse_mode="HTML"
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

        found_responses = False

        for vacancy in vacancies[:10]:

            responses = await repo.list_vacancy_responses(
                vacancy["id"]
            )

            if not responses:
                continue

            found_responses = True

            status = vacancy.get("status")

            status_text = {
                "approved": "✅ Активна",
                "pending": "⏳ На модерации",
                "rejected": "❌ Отклонена",
                "closed": "🔒 Закрыта",
            }.get(status, status)

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

        if not found_responses:

            await message.answer(
                "📭 На ваши вакансии пока никто не откликнулся."
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

        await callback.answer()

        return

    for response in responses[:10]:

        seeker = await repo.get_seeker(
            response["seeker_id"]
        )

        if not seeker:
            continue

        salary = format_salary(
            seeker.get("salary_min"),
            seeker.get("salary_max")
        )

        contacts = seeker.get(
            "contacts",
            "не указаны"
        )

        candidate_text = (
            f"👤 {seeker.get('full_name', 'Без имени')}\n"
            f"📍 {seeker.get('city') or 'Не указан'}\n"
            f"💰 {salary}\n"
            f"📞 {contacts}"
        )

        await callback.message.answer(
            candidate_text,
            reply_markup=candidate_preview_keyboard(
                seeker["user_id"]
            )
        )

    await callback.answer()

@router.callback_query(
    F.data.startswith("candidate:")
)
async def candidate_details(
    callback: CallbackQuery,
    repo: SupabaseRepository
):

    seeker_id = int(
        callback.data.split(":")[1]
    )

    seeker = await repo.get_seeker(
        seeker_id
    )

    if not seeker:

        await callback.answer(
            "Кандидат не найден",
            show_alert=True
        )

        return

    salary = format_salary(
        seeker.get("salary_min"),
        seeker.get("salary_max")
    )

    username = seeker.get("username")

    if username:
        username = f"@{username}"
    else:
        username = "не указан"

    text = (
        f"👤 {seeker.get('full_name') or 'Не указано'}\n\n"

        f"🎂 Возраст: {seeker.get('age') or 'Не указан'}\n"
        f"📍 Город: {seeker.get('city') or 'Не указан'}\n\n"

        f"💼 Желаемые должности:\n"
        f"{seeker.get('desired_positions') or 'Не указано'}\n\n"

        f"🏭 Сфера:\n"
        f"{seeker.get('sphere') or 'Не указано'}\n\n"

        f"🕒 График:\n"
        f"{seeker.get('schedule') or 'Не указано'}\n\n"

        f"💰 Зарплатные ожидания:\n"
        f"{salary}\n\n"

        f"🛠 Навыки:\n"
        f"{seeker.get('skills') or 'Не указано'}\n\n"

        f"📝 О себе:\n"
        f"{seeker.get('about') or 'Не указано'}\n\n"

        f"📞 Контакты:\n"
        f"{seeker.get('contacts') or 'Не указаны'}\n"

        f"☎️ Телефон:\n"
        f"{seeker.get('phone') or 'Не указан'}\n"

        f"📨 Telegram:\n"
        f"{username}"
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
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    await state.clear()

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

@router.message(F.text == "🏢 Моя компания")
async def my_company(
    message: Message,
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    await state.clear()

    company = await repo.get_company_by_owner(
        message.from_user.id
    )

    if not company:

        await message.answer(
            "🏢 <b>Карточка компании</b>\n\n"

            "Рекомендуем создать карточку компании перед публикацией вакансий.\n\n"

            "Это поможет системе:\n"
            "• точнее подбирать сотрудников\n"
            "• рекомендовать компанию подходящим кандидатам\n"
            "• улучшить будущий AI-подбор\n"
            "• повысить количество откликов\n\n"

            "Карточка компании не обязательна.\n"
            "Вы можете публиковать вакансии и без неё.",

            parse_mode="HTML",
            reply_markup=company_start_keyboard()
        )

        return

    await message.answer(
        f"🏢 {company['name']}\n\n"

        f"🏭 Сфера деятельности:\n"
        f"{company.get('industry') or 'Не указано'}\n\n"

        f"👥 Обычно ищем:\n"
        f"{company.get('hiring_keywords') or 'Не указано'}\n\n"

        f"📍 Город:\n"
        f"{company.get('city') or 'Не указано'}\n\n"

        f"📞 Контакты:\n"
        f"{company.get('contacts') or 'Не указано'}\n\n"

        f"📝 Описание:\n"
        f"{company.get('description') or 'Описание отсутствует'}",
        reply_markup=company_keyboard()
    )


@router.message(F.text == "📋 Мои вакансии")
async def my_vacancies(
    message: Message,
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    await state.clear()

    vacancies = await repo.list_employer_vacancies(
        message.from_user.id
    )

    if not vacancies:

        await message.answer(
            "📭 У вас пока нет вакансий."
        )

        return

    for vacancy in vacancies:

        status = {
            "approved": "✅ Активна",
            "pending": "⏳ На модерации",
            "rejected": "❌ Отклонена",
            "closed": "🔒 Закрыта",
        }.get(
            vacancy.get("status"),
            vacancy.get("status")
        )

        await message.answer(
            f"💼 {vacancy['title']}\n"
            f"{status}",
            reply_markup=employer_vacancy_keyboard(
                vacancy["id"]
            )
        )


@router.message(F.text == "📢 Разместить вакансию")
async def vacancy_start(
    message: Message,
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    logger.warning(
        f"VACANCY_START CLICKED | text={message.text}"
    )

    current_state = await state.get_state()

    logger.warning(
        f"VACANCY_START BEFORE CLEAR | state={current_state}"
    )

    await state.clear()

    current_state = await state.get_state()

    logger.warning(
        f"VACANCY_START AFTER CLEAR | state={current_state}"
    )

    company = await repo.get_company_by_owner(
        message.from_user.id
    )

    logger.warning(
        f"VACANCY_START COMPANY FOUND = {bool(company)}"
    )

    if company:

        await state.update_data(
            company_id=company["id"],
            company_name=company["name"]
        )

        await state.set_state(
            VacancyForm.title
        )

        logger.warning(
            "VACANCY_START -> VacancyForm.title"
        )

        await message.answer(
            f"🏢 Компания: {company['name']}\n\n"
            "Введите название вакансии.\n\n"
            "Например:\n"
            "Продавец\n"
            "Менеджер\n"
            "Водитель"
        )

        return

    await state.set_state(
        CompanyForm.intro
    )

    logger.warning(
        "VACANCY_START -> CompanyForm.intro"
    )

    await message.answer(
        "<b>🏢 Рекомендуем создать карточку компании</b>\n\n"

        "От качества заполнения карточки зависит скорость подбора сотрудников.\n\n"

        "Система сможет:\n"
        "• рекомендовать вашу компанию кандидатам\n"
        "• подбирать более подходящих сотрудников\n"
        "• доставлять отклики прямо в личный кабинет\n\n"

        "Также соискатели смогут отправлять свои анкеты напрямую работодателям.\n\n"

        "Все отклики будут приходить в ваш личный кабинет.\n\n"

        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=company_start_keyboard()
    )

@router.message(
    F.text == "⏭ Продолжить без карточки"
)
async def vacancy_without_company(
    message: Message,
    state: FSMContext
) -> None:

    await state.set_state(
        VacancyForm.title
    )

    await message.answer(
        "💼 Введите название вакансии.\n\n"
        "Например:\n"
        "Продавец\n"
        "Менеджер\n"
        "Водитель"
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


async def show_edit_vacancy(
    message: Message,
    vacancy_id: int,
    repo: SupabaseRepository
) -> None:

    vacancy = await repo.get_vacancy(
        vacancy_id
    )

    if not vacancy:

        await message.answer(
            "❌ Вакансия не найдена."
        )

        return

    salary = format_salary(
        vacancy.get("salary_min"),
        vacancy.get("salary_max")
    )

    await message.answer(
        f"📄 <b>Текущая вакансия</b>\n\n"

        f"💼 <b>Название</b>\n"
        f"{vacancy.get('title')}\n\n"

        f"💰 <b>Зарплата</b>\n"
        f"{salary}\n\n"

        f"🕒 <b>График</b>\n"
        f"{vacancy.get('schedule')}\n\n"

        f"📋 <b>Описание</b>\n"
        f"{vacancy.get('description')}\n\n"

        f"📞 <b>Контакты</b>\n"
        f"{vacancy.get('contacts') or 'Не указано'}\n\n"

        "✏️ Что хотите изменить?",

        parse_mode="HTML",

        reply_markup=edit_vacancy_keyboard(
            vacancy_id
        )
    )


@router.callback_query(
    F.data.startswith("edit_vacancy:")
)
async def edit_vacancy(
    callback: CallbackQuery,
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    vacancy_id = int(
        callback.data.split(":")[1]
    )

    await state.update_data(
        edit_vacancy_id=vacancy_id
    )

    await show_edit_vacancy(
        callback.message,
        vacancy_id,
        repo
    )

    await callback.answer()



@router.callback_query(
    F.data.startswith("edit_contacts:")
)
async def edit_vacancy_contacts(
    callback: CallbackQuery,
    state: FSMContext
) -> None:

    vacancy_id = int(
        callback.data.split(":")[1]
    )

    await state.update_data(
        edit_vacancy_id=vacancy_id
    )

    await state.set_state(
        EditVacancyForm.waiting_contacts
    )

    await callback.message.answer(
        "📞 Введите новые контакты:"
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("edit_title:")
)
async def edit_vacancy_title(
    callback: CallbackQuery,
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    vacancy_id = int(
        callback.data.split(":")[1]
    )

    vacancy = await repo.get_vacancy(
        vacancy_id
    )

    if not vacancy:

        await callback.message.answer(
            "❌ Вакансия не найдена."
        )

        await callback.answer()

        return

    await state.update_data(
        edit_vacancy_id=vacancy_id
    )

    await state.set_state(
        EditVacancyForm.waiting_title
    )

    await callback.message.answer(
        f"💼 Текущее название:\n\n"
        f"{vacancy.get('title')}\n\n"
        f"Введите новое название вакансии:"
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("edit_salary:")
)
async def edit_vacancy_salary(
    callback: CallbackQuery,
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    vacancy_id = int(
        callback.data.split(":")[1]
    )

    vacancy = await repo.get_vacancy(
        vacancy_id
    )

    if not vacancy:

        await callback.message.answer(
            "❌ Вакансия не найдена."
        )

        await callback.answer()

        return

    current_salary = format_salary(
        vacancy.get("salary_min"),
        vacancy.get("salary_max")
    )

    await state.update_data(
        edit_vacancy_id=vacancy_id
    )

    await state.set_state(
        EditVacancyForm.waiting_salary
    )

    await callback.message.answer(
        f"💰 Текущая зарплата:\n\n"
        f"{current_salary}\n\n"
        f"Введите новую зарплату.\n\n"
        f"Примеры:\n"
        f"200\n"
        f"350\n"
        f"500\n\n"
        f"Или диапазон:\n"
        f"200-300\n"
        f"350-500"
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("edit_schedule:")
)
async def edit_vacancy_schedule(
    callback: CallbackQuery,
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    vacancy_id = int(
        callback.data.split(":")[1]
    )

    vacancy = await repo.get_vacancy(
        vacancy_id
    )

    if not vacancy:

        await callback.message.answer(
            "❌ Вакансия не найдена."
        )

        await callback.answer()

        return

    current_schedule = (
        vacancy.get("schedule")
        or "Не указан"
    )

    await state.update_data(
        edit_vacancy_id=vacancy_id
    )

    await state.set_state(
        EditVacancyForm.waiting_schedule
    )

    await callback.message.answer(
        f"🕒 Текущий график:\n\n"
        f"{current_schedule}\n\n"
        f"Выберите новый график:",
        reply_markup=schedules_keyboard(
            "edit_schedule_value"
        )
    )

    await callback.answer()



@router.callback_query(
    EditVacancyForm.waiting_schedule,
    F.data.startswith("edit_schedule_value:")
)
async def select_vacancy_schedule(
    callback: CallbackQuery,
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    data = await state.get_data()

    vacancy_id = data.get(
        "edit_vacancy_id"
    )

    if not vacancy_id:

        await callback.message.answer(
            "❌ Вакансия не найдена."
        )

        await state.clear()

        await callback.answer()

        return

    vacancy = await repo.get_vacancy(
        vacancy_id
    )

    if not vacancy:

        await callback.message.answer(
            "❌ Вакансия не найдена."
        )

        await state.clear()

        await callback.answer()

        return

    new_schedule = callback.data.split(
        ":",
        1
    )[1]

    await state.update_data(
        new_schedule=new_schedule
    )

    await state.set_state(
        EditVacancyForm.confirm_schedule
    )

    old_schedule = (
        vacancy.get("schedule")
        or "Не указан"
    )

    await callback.message.answer(
        "🕒 Изменение графика\n\n"

        f"🔹 Было:\n"
        f"{old_schedule}\n\n"

        f"🔹 Станет:\n"
        f"{new_schedule}\n\n"

        "Сохранить изменения?",

        reply_markup=confirm_schedule_edit_keyboard()
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("edit_description:")
)
async def edit_vacancy_description(
    callback: CallbackQuery,
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    vacancy_id = int(
        callback.data.split(":")[1]
    )

    vacancy = await repo.get_vacancy(
        vacancy_id
    )

    if not vacancy:

        await callback.message.answer(
            "❌ Вакансия не найдена."
        )

        await callback.answer()

        return

    await state.update_data(
        edit_vacancy_id=vacancy_id
    )

    await state.set_state(
        EditVacancyForm.waiting_description
    )

    await callback.message.answer(
        f"📋 Текущее описание:\n\n"
        f"{vacancy.get('description')}\n\n"
        f"Введите новое описание:"
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("edit_contacts:")
)
async def edit_vacancy_contacts(
    callback: CallbackQuery,
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    vacancy_id = int(
        callback.data.split(":")[1]
    )

    vacancy = await repo.get_vacancy(
        vacancy_id
    )

    if not vacancy:

        await callback.message.answer(
            "❌ Вакансия не найдена."
        )

        await callback.answer()

        return

    await state.update_data(
        edit_vacancy_id=vacancy_id
    )

    await state.set_state(
        EditVacancyForm.waiting_contacts
    )

    await callback.message.answer(
        f"📞 Текущие контакты:\n\n"
        f"{vacancy.get('contacts') or 'Не указано'}\n\n"
        f"Введите новые контакты:"
    )

    await callback.answer()


@router.message(
    EditVacancyForm.waiting_contacts
)
async def save_vacancy_contacts(
    message: Message,
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    data = await state.get_data()

    vacancy_id = data.get(
        "edit_vacancy_id"
    )

    if not vacancy_id:

        await message.answer(
            "❌ Вакансия не найдена."
        )

        await state.clear()

        return

    vacancy = await repo.get_vacancy(
        vacancy_id
    )

    if not vacancy:

        await message.answer(
            "❌ Вакансия не найдена."
        )

        await state.clear()

        return

    old_contacts = (
        vacancy.get("contacts")
        or "Не указано"
    )

    new_contacts = (
        message.text or ""
    ).strip()

    await state.update_data(
        new_contacts=new_contacts
    )

    await state.set_state(
        EditVacancyForm.confirm_contacts
    )

    await message.answer(
        "📞 Изменение контактов\n\n"

        f"🔹 Было:\n"
        f"{old_contacts}\n\n"

        f"🔹 Станет:\n"
        f"{new_contacts}\n\n"

        "Сохранить изменения?",

        reply_markup=confirm_contacts_edit_keyboard()
    )


@router.message(
    EditVacancyForm.waiting_title
)
async def save_vacancy_title(
    message: Message,
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    data = await state.get_data()

    vacancy_id = data.get(
        "edit_vacancy_id"
    )

    if not vacancy_id:

        await message.answer(
            "❌ Вакансия не найдена."
        )

        await state.clear()

        return

    vacancy = await repo.get_vacancy(
        vacancy_id
    )

    if not vacancy:

        await message.answer(
            "❌ Вакансия не найдена."
        )

        await state.clear()

        return

    old_title = (
        vacancy.get("title")
        or "Без названия"
    )

    new_title = (
        message.text or ""
    ).strip()

    await state.update_data(
        new_title=new_title
    )

    await state.set_state(
        EditVacancyForm.confirm_title
    )

    await message.answer(
        "💼 Изменение названия\n\n"

        f"🔹 Было:\n"
        f"{old_title}\n\n"

        f"🔹 Станет:\n"
        f"{new_title}\n\n"

        "Сохранить изменения?",

        reply_markup=confirm_title_edit_keyboard()
    )


@router.message(
    EditVacancyForm.waiting_salary
)
async def save_vacancy_salary(
    message: Message,
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    data = await state.get_data()

    vacancy_id = data.get(
        "edit_vacancy_id"
    )

    if not vacancy_id:

        await message.answer(
            "❌ Вакансия не найдена."
        )

        await state.clear()

        return

    vacancy = await repo.get_vacancy(
        vacancy_id
    )

    if not vacancy:

        await message.answer(
            "❌ Вакансия не найдена."
        )

        await state.clear()

        return

    text = (
        message.text or ""
    ).strip()

    try:

        salary_min, salary_max = (
            parse_salary_range(text)
        )

    except ValueError:

        await message.answer(
            "❌ Не понял сумму.\n\n"
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
        new_salary_min=salary_min,
        new_salary_max=salary_max
    )

    await state.set_state(
        EditVacancyForm.confirm_salary
    )

    old_salary = format_salary(
        vacancy.get("salary_min"),
        vacancy.get("salary_max")
    )

    new_salary = format_salary(
        salary_min,
        salary_max
    )

    await message.answer(
        "💰 Изменение зарплаты\n\n"

        f"🔹 Было:\n"
        f"{old_salary}\n\n"

        f"🔹 Станет:\n"
        f"{new_salary}\n\n"

        "Сохранить изменения?",

        reply_markup=confirm_salary_edit_keyboard()
    )


@router.message(
    EditVacancyForm.waiting_schedule
)
async def save_vacancy_schedule(
    message: Message,
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    data = await state.get_data()
    vacancy_id = data.get("edit_vacancy_id")

    if not vacancy_id:
        await message.answer("❌ Вакансия не найдена.")
        await state.clear()
        return

    await repo.update_vacancy_field(
        vacancy_id=vacancy_id,
        employer_id=message.from_user.id,
        field="schedule",
        value=(message.text or "").strip()
    )

    vacancy = await repo.get_vacancy(vacancy_id)

    await state.clear()

    await message.answer(
        f"✅ График обновлён.\n\n"
        f"💼 {vacancy.get('title')}\n"
        f"🕒 {vacancy.get('schedule')}"
    )


@router.message(
    EditVacancyForm.waiting_description
)
async def save_vacancy_description(
    message: Message,
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    data = await state.get_data()

    vacancy_id = data.get(
        "edit_vacancy_id"
    )

    if not vacancy_id:

        await message.answer(
            "❌ Вакансия не найдена."
        )

        await state.clear()

        return

    vacancy = await repo.get_vacancy(
        vacancy_id
    )

    if not vacancy:

        await message.answer(
            "❌ Вакансия не найдена."
        )

        await state.clear()

        return

    old_description = (
        vacancy.get("description")
        or "Не указано"
    )

    new_description = (
        message.text or ""
    ).strip()

    await state.update_data(
        new_description=new_description
    )

    await state.set_state(
        EditVacancyForm.confirm_description
    )

    await message.answer(
        "📋 Изменение описания\n\n"

        f"🔹 Было:\n"
        f"{old_description}\n\n"

        f"🔹 Станет:\n"
        f"{new_description}\n\n"

        "Сохранить изменения?",

        reply_markup=confirm_vacancy_edit_keyboard()
    )


@router.callback_query(
    F.data == "confirm_vacancy_edit"
)
async def confirm_vacancy_description_edit(
    callback: CallbackQuery,
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    data = await state.get_data()

    vacancy_id = data.get(
        "edit_vacancy_id"
    )

    new_description = data.get(
        "new_description"
    )

    if not vacancy_id:

        await callback.message.answer(
            "❌ Вакансия не найдена."
        )

        await state.clear()

        await callback.answer()

        return

    await repo.update_vacancy_field(
        vacancy_id=vacancy_id,
        employer_id=callback.from_user.id,
        field="description",
        value=new_description
    )

    vacancy = await repo.get_vacancy(
        vacancy_id
    )

    await state.clear()

    await callback.message.answer(
        "✅ Изменения сохранены."
    )

    await show_edit_vacancy(
        callback.message,
        vacancy_id,
        repo
    )

    await callback.answer()


@router.callback_query(
    F.data == "confirm_salary_edit"
)
async def confirm_salary_edit(
    callback: CallbackQuery,
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    data = await state.get_data()

    vacancy_id = data.get(
        "edit_vacancy_id"
    )

    salary_min = data.get(
        "new_salary_min"
    )

    salary_max = data.get(
        "new_salary_max"
    )

    if not vacancy_id:

        await callback.message.answer(
            "❌ Вакансия не найдена."
        )

        await state.clear()

        await callback.answer()

        return

    await repo.update_vacancy_field(
        vacancy_id=vacancy_id,
        employer_id=callback.from_user.id,
        field="salary_min",
        value=salary_min
    )

    await repo.update_vacancy_field(
        vacancy_id=vacancy_id,
        employer_id=callback.from_user.id,
        field="salary_max",
        value=salary_max
    )

    vacancy = await repo.get_vacancy(
        vacancy_id
    )

    await state.clear()

    await callback.message.answer(
        "✅ Изменения сохранены."
    )

    await show_edit_vacancy(
        callback.message,
        vacancy_id,
        repo
    )

    await callback.answer()


@router.callback_query(
    F.data == "confirm_schedule_edit"
)
async def confirm_schedule_edit(
    callback: CallbackQuery,
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    data = await state.get_data()

    vacancy_id = data.get(
        "edit_vacancy_id"
    )

    new_schedule = data.get(
        "new_schedule"
    )

    if not vacancy_id:

        await callback.message.answer(
            "❌ Вакансия не найдена."
        )

        await state.clear()

        await callback.answer()

        return

    await repo.update_vacancy_field(
        vacancy_id=vacancy_id,
        employer_id=callback.from_user.id,
        field="schedule",
        value=new_schedule
    )

    vacancy = await repo.get_vacancy(
        vacancy_id
    )

    await state.clear()

    await callback.message.answer(
        "✅ Изменения сохранены."
    )

    await show_edit_vacancy(
        callback.message,
        vacancy_id,
        repo
    )

    await callback.answer()


@router.callback_query(
    F.data == "confirm_title_edit"
)
async def confirm_title_edit(
    callback: CallbackQuery,
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    data = await state.get_data()

    vacancy_id = data.get(
        "edit_vacancy_id"
    )

    new_title = data.get(
        "new_title"
    )

    if not vacancy_id:

        await callback.message.answer(
            "❌ Вакансия не найдена."
        )

        await state.clear()

        await callback.answer()

        return

    await repo.update_vacancy_field(
        vacancy_id=vacancy_id,
        employer_id=callback.from_user.id,
        field="title",
        value=new_title
    )

    vacancy = await repo.get_vacancy(
        vacancy_id
    )

    await state.clear()

    await callback.message.answer(
        "✅ Название сохранено."
    )

    await show_edit_vacancy(
        callback.message,
        vacancy_id,
        repo
    )

    await callback.answer()


@router.callback_query(
    F.data == "cancel_title_edit"
)
async def cancel_title_edit(
    callback: CallbackQuery,
    state: FSMContext
) -> None:

    await state.clear()

    await callback.message.answer(
        "❌ Изменение названия отменено."
    )

    await callback.answer()




@router.callback_query(
    F.data == "cancel_schedule_edit"
)
async def cancel_schedule_edit(
    callback: CallbackQuery,
    state: FSMContext
) -> None:

    await state.clear()

    await callback.message.answer(
        "❌ Изменение графика отменено."
    )

    await callback.answer()



@router.callback_query(
    F.data == "cancel_salary_edit"
)
async def cancel_salary_edit(
    callback: CallbackQuery,
    state: FSMContext
) -> None:

    await state.clear()

    await callback.message.answer(
        "❌ Изменение зарплаты отменено."
    )

    await callback.answer()


@router.callback_query(
    F.data == "cancel_vacancy_edit"
)
async def cancel_vacancy_description_edit(
    callback: CallbackQuery,
    state: FSMContext
) -> None:

    await state.clear()

    await callback.message.answer(
        "❌ Изменение отменено."
    )

    await callback.answer()


@router.callback_query(
    F.data == "confirm_contacts_edit"
)
async def confirm_contacts_edit(
    callback: CallbackQuery,
    state: FSMContext,
    repo: SupabaseRepository
) -> None:

    data = await state.get_data()

    vacancy_id = data.get(
        "edit_vacancy_id"
    )

    new_contacts = data.get(
        "new_contacts"
    )

    if not vacancy_id:

        await callback.message.answer(
            "❌ Вакансия не найдена."
        )

        await state.clear()

        await callback.answer()

        return

    await repo.update_vacancy_field(
        vacancy_id=vacancy_id,
        employer_id=callback.from_user.id,
        field="contacts",
        value=new_contacts
    )

    await state.clear()

    await callback.message.answer(
        "✅ Контакты сохранены."
    )

    await show_edit_vacancy(
        callback.message,
        vacancy_id,
        repo
    )

    await callback.answer()


@router.callback_query(
    F.data == "cancel_contacts_edit"
)
async def cancel_contacts_edit(
    callback: CallbackQuery,
    state: FSMContext
) -> None:

    await state.clear()

    await callback.message.answer(
        "❌ Изменение контактов отменено."
    )

    await callback.answer()



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

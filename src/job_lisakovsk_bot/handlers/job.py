from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

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
    admin_manual_payment_keyboard,
    buy_unlimited_keyboard,
    channel_post_keyboard,
    employer_feedback_keyboard,
    main_menu,
    manual_payment_keyboard,
    moderation_keyboard,
    schedules_keyboard,
    seeker_feedback_keyboard,
    seeker_vip_keyboard,
    spheres_keyboard,
    vacancies_keyboard,
    vacancy_paid_features_keyboard,
)
from job_lisakovsk_bot.services.job_text import (
    admin_stats_text,
    employer_stats_text,
    seeker_card,
    seeker_stats_text,
    vacancy_private_text,
    vacancy_public_text,
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

logger = logging.getLogger(__name__)
router = Router(name="job")

@router.message(Command("test"))
async def test_command(message: Message):
    await message.answer("✅ Бот работает, хендлеры зарегистрированы")

async def get_user_role(user_id: int, repo: SupabaseRepository) -> str | None:
    # Сначала проверяем сохранённую роль
    result = await repo.get_user_active_role(user_id)
    if result:
        return result["role"]
    
    # Если нет сохранённой роли, определяем по данным
    employer_vacancies = await repo.count_employer_vacancies(user_id)
    seeker = await repo.get_seeker(user_id)
    
    # Приоритет: если есть вакансии → работодатель, иначе если есть анкета → соискатель
    if employer_vacancies > 0:
        role = "employer"
    elif seeker:
        role = "seeker"
    else:
        return None
    
    # Сохраняем определённую роль
    await repo.set_user_active_role(user_id, role)
    return role


@router.message(F.text == "🔄 Переключиться на соискателя")
@router.message(F.text == "🔄 Переключиться на работодателя")
async def toggle_role(message: Message, repo: SupabaseRepository):
    current_role = await get_user_role(message.from_user.id, repo)
    
    if not current_role:
        await message.answer(
            "❌ Сначала заполните анкету соискателя или создайте вакансию.\n\n"
            "После этого появится возможность переключаться между ролями."
        )
        return
    
    new_role = "seeker" if current_role == "employer" else "employer"
    await repo.set_user_active_role(message.from_user.id, new_role)
    
    role_name = "Соискатель" if new_role == "seeker" else "Работодатель"
    
    await message.answer(
        f"✅ Вы переключились в режим «{role_name}»\n\n"
        f"Теперь вам доступны соответствующие функции бота.\n\n"
        f"Выберите действие в меню ниже 👇",
        reply_markup=main_menu(user_role=new_role)
    )


class SeekerForm(StatesGroup):
    sphere = State()
    schedule = State()
    salary = State()
    about = State()


class VacancyForm(StatesGroup):
    title = State()
    sphere = State()
    schedule = State()
    salary = State()
    contacts = State()
    description = State()


class RejectVacancyForm(StatesGroup):
    reason = State()


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
        await bot.pin_chat_message(settings.channel_id, vacancy["channel_message_id"], disable_notification=True)
        await repo.schedule_unpin(vacancy_id, vacancy["channel_message_id"], datetime.now(UTC) + timedelta(days=3))
        return "📌 Вакансия закреплена в канале на 3 дня."

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
async def start(message: Message, state: FSMContext, command: CommandObject, repo: SupabaseRepository, settings: Settings) -> None:
    arg = command.args
    referrer_id = parse_referral_arg(arg)
    
    if referrer_id is not None:
        await repo.register_referral(referrer_id, message.from_user.id)
        await message.answer(
            "🎉 Реферальная ссылка учтена!\n\n"
            "Добро пожаловать в «Работа Лисаковск»!\n\n"
            "Выберите действие в меню ниже 👇",
            reply_markup=main_menu()
        )
        return
    
    if arg and arg.startswith("apply_"):
        vacancy_id = int(arg.split("_")[1])
        await apply_vacancy_start(message, vacancy_id, repo, settings, bot)
        return
    
    if arg == "resume":
        await seeker_start(message, state)
        return
    
    if arg == "vacancy":
        await vacancy_start(message, state)
        return
    
    user_role = await get_user_role(message.from_user.id, repo)
    
    await message.answer(
        "👋 Привет! Это бот «Работа Лисаковск».\n\n"
        "📌 *Соискатель* — заполните анкету, получайте подходящие вакансии\n\n"
        "📢 *Работодатель* — разместите вакансию, наймите сотрудников\n\n"
        "Выберите действие в меню ниже 👇",
        parse_mode="Markdown",
        reply_markup=main_menu(user_role),
    )

@router.message(Command("resume"))
async def cmd_resume(message: Message, state: FSMContext):
    await seeker_start(message, state)


@router.message(Command("vacancy"))
async def cmd_vacancy(message: Message, state: FSMContext):
    await vacancy_start(message, state)


async def apply_vacancy_start(
    message: Message,
    vacancy_id: int,
    repo: SupabaseRepository,
    settings: Settings,
    bot: Bot
) -> None:
    try:
        seeker = await repo.get_seeker(message.from_user.id)
        vacancy = await repo.get_vacancy(vacancy_id)
        
        if not vacancy or vacancy["status"] != "approved":
            await message.answer("❌ Вакансия не найдена или уже закрыта.")
            return
        
        if not seeker:
            await message.answer(
                "🔍 Чтобы откликнуться, сначала заполните анкету соискателя.\n\n"
                "Нажмите /start resume",
                reply_markup=main_menu()
            )
            return
        
        await message.answer(
            vacancy_private_text(vacancy, settings.bot_username),
            reply_markup=vacancies_keyboard(vacancy_id)
        )
    except Exception as e:
        logger.error(f"Error in apply_vacancy_start: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


@router.message(F.text == "Ищу работу")
async def seeker_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(SeekerForm.sphere)
    await message.answer("📂 Выберите сферу:", reply_markup=spheres_keyboard("seeker_sphere"))


@router.callback_query(SeekerForm.sphere, F.data.startswith("seeker_sphere:"))
async def seeker_sphere(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(sphere=callback.data.split(":", 1)[1])
    await state.set_state(SeekerForm.schedule)
    await callback.message.edit_text("📅 Выберите график:", reply_markup=schedules_keyboard("seeker_schedule"))
    await callback.answer()


@router.callback_query(SeekerForm.schedule, F.data.startswith("seeker_schedule:"))
async def seeker_schedule(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(schedule=callback.data.split(":", 1)[1])
    await state.set_state(SeekerForm.salary)
    await callback.message.edit_text(
        "💰 Укажите зарплату от и до, например: 200000-300000.\nЕсли не важно — напишите «Не важно»."
    )
    await callback.answer()


@router.message(SeekerForm.salary)
async def seeker_salary(message: Message, state: FSMContext) -> None:
    text = message.text or ""
    if text.lower() in ["не важно", "договорная", "договор"]:
        await state.update_data(salary_min=None, salary_max=None, salary_text="Договорная")
    else:
        try:
            salary_min, salary_max = parse_salary_range(text)
            await state.update_data(salary_min=salary_min, salary_max=salary_max, salary_text=f"{salary_min}-{salary_max} ₸")
        except ValueError:
            await message.answer("❌ Не понял сумму. Напишите диапазон вроде 200000-300000, «Не важно» или «Договорная».")
            return
    
    await state.set_state(SeekerForm.about)
    await message.answer("📝 Коротко о себе одним предложением. Например: «Сварщик с опытом 5 лет, есть свой инструмент».")


@router.message(SeekerForm.about)
async def seeker_about(message: Message, state: FSMContext, repo: SupabaseRepository) -> None:
    try:
        data = await state.get_data()
        referred_by = await repo.get_referrer_for_user(message.from_user.id)
        payload = {
            "user_id": message.from_user.id,
            "username": message.from_user.username,
            "sphere": data["sphere"],
            "schedule": data["schedule"],
            "salary_min": data["salary_min"],
            "salary_max": data["salary_max"],
            "about": (message.text or "").strip(),
            "active": True,
        }
        if referred_by is not None:
            payload["referred_by"] = referred_by
        await repo.upsert_seeker(payload)
        await state.clear()
        await message.answer(
            "✅ Ты в базе! Когда появится подходящая вакансия — я пришлю уведомление.\n"
            "Пока можешь посмотреть открытые вакансии.",
            reply_markup=main_menu(),
        )
    except Exception as e:
        logger.error(f"Error in seeker_about: {e}")
        await message.answer("❌ Ошибка при сохранении анкеты. Попробуйте позже.")


@router.message(F.text.in_({"🔍 Смотреть вакансии", "/vacancies"}))
async def show_vacancies(message: Message, repo: SupabaseRepository, settings: Settings) -> None:
    try:
        seeker = await repo.get_seeker(message.from_user.id)
        vacancies = await repo.list_active_vacancies(sphere=seeker["sphere"] if seeker else None)
        if not vacancies:
            await message.answer("📭 Пока активных вакансий нет. Как только появятся — пришлю уведомление.")
            return

        for vacancy in vacancies:
            await message.answer(
                vacancy_private_text(vacancy, settings.bot_username),
                reply_markup=vacancies_keyboard(vacancy["id"]),
            )
    except Exception as e:
        logger.error(f"Error in show_vacancies: {e}")
        await message.answer("❌ Ошибка при загрузке вакансий. Попробуйте позже.")


@router.message(F.text == "📢 Разместить вакансию")
async def vacancy_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(VacancyForm.title)
    await message.answer("👔 Кого ищете? Напишите должность или услугу. Например: «сварщик» или «бариста».")


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
    await callback.message.edit_text("💰 Укажите зарплату от и до, например: 250000-300000.")
    await callback.answer()


@router.message(VacancyForm.salary)
async def vacancy_salary(message: Message, state: FSMContext) -> None:
    try:
        salary_min, salary_max = parse_salary_range(message.text or "")
    except ValueError:
        await message.answer("❌ Не понял сумму. Напишите диапазон вроде 250000-300000.")
        return
    await state.update_data(salary_min=salary_min, salary_max=salary_max)
    await state.set_state(VacancyForm.contacts)
    await message.answer("📞 Оставьте контакты: телефон или @username.")


@router.message(VacancyForm.contacts)
async def vacancy_contacts(message: Message, state: FSMContext) -> None:
    await state.update_data(contacts=(message.text or "").strip())
    await state.set_state(VacancyForm.description)
    await message.answer("📝 Опишите, что требуется от кандидата.")


@router.message(VacancyForm.description)
async def vacancy_description(
    message: Message,
    state: FSMContext,
    repo: SupabaseRepository,
    settings: Settings,
    bot: Bot,
) -> None:
    try:
        usage = await repo.get_or_create_usage(message.from_user.id)
        referrals = await repo.count_referrals(message.from_user.id)
        has_unlimited = await repo.has_unlimited_vacancies(message.from_user.id)
        decision = can_create_vacancy(int(usage.get("vacancies_this_month") or 0), referrals, has_unlimited)
        
        if not decision.allowed:
            await message.answer(
                f"⚠️ Бесплатный лимит вакансий на месяц исчерпан ({decision.used}/{decision.limit}).\n\n"
                f"💳 Можно купить безлимит за 500 ₸ или пригласить друга.",
                reply_markup=buy_unlimited_keyboard(),
            )
            return

        data = await state.get_data()
        referred_by = await repo.get_referrer_for_user(message.from_user.id)
        payload = {
            "employer_id": message.from_user.id,
            "employer_username": message.from_user.username,
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
        await repo.increment_vacancies_this_month(message.from_user.id)
        await state.clear()
        await message.answer("✅ Вакансия отправлена на модерацию. После проверки я сообщу результат.", reply_markup=main_menu())
        await bot.send_message(
            settings.admin_chat_id,
            "🆕 Новая вакансия на модерацию:\n\n" + vacancy_public_text(vacancy, settings.bot_username),
            reply_markup=moderation_keyboard(vacancy["id"]),
        )
    except Exception as e:
        logger.error(f"Error in vacancy_description: {e}")
        await message.answer("❌ Ошибка при создании вакансии. Попробуйте позже.")


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
    await bot.send_message(
        vacancy["employer_id"],
        "✅ Ваша вакансия одобрена и опубликована в канале. Хотите ускорить поиск?",
        reply_markup=vacancy_paid_features_keyboard(vacancy_id),
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
    vacancy = await repo.get_vacancy(vacancy_id)
    seeker = await repo.get_seeker(callback.from_user.id)
    if not vacancy or not seeker:
        await callback.answer("❌ Сначала заполните анкету соискателя.", show_alert=True)
        return

    await repo.set_reaction(vacancy_id, callback.from_user.id, "like")
    contact = f"@{callback.from_user.username}" if callback.from_user.username else f"telegram id {callback.from_user.id}"
    await bot.send_message(
        vacancy["employer_id"],
        f"📩 На вашу вакансию откликнулся соискатель:\n\n"
        f"{seeker_card(seeker)}\n\n📞 Контакты: {contact}",
    )
    await callback.answer("✅ Отклик отправлен работодателю!", show_alert=True)


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
        
        await manual_payment_start(callback, repo, settings)
        
    except Exception as e:
        logger.error(f"Error in buy_feature: {e}")
        await callback.answer("❌ Ошибка. Попробуйте позже.", show_alert=True)


@router.callback_query(F.data.startswith("manual:"))
async def manual_payment_start(callback: CallbackQuery, repo: SupabaseRepository, settings: Settings) -> None:
    _, feature, *rest = callback.data.split(":")
    vacancy_id = int(rest[0]) if rest else None
    request = get_feature_request(feature, vacancy_id)
    
    payment = await repo.create_payment(
        user_id=callback.from_user.id,
        payment_type=PAYMENT_TYPE_MANUAL,
        amount=request.amount,
        feature=feature,
        vacancy_id=vacancy_id,
    )
    
    await callback.message.answer(
    f"💳 *Оплата функции*\n\n"
    f"┌─────────────────────┐\n"
    f"│ 📦 {request.title}\n"
    f"│ 💰 Сумма: *{request.amount} ₸*\n"
    f"└─────────────────────┘\n\n"
    f"📱 *Переведите {request.amount} ₸ на номер Билайн:*\n"
    f"`{settings.beeline_payment_phone}`\n\n"
    f"📲 *Как оплатить:*\n"
    f"1. Откройте приложение банка\n"
    f"2. Выберите «Платежи» → «Мобильная связь»\n"
    f"3. Введите номер: `{settings.beeline_payment_phone}`\n"
    f"4. Укажите сумму: *{request.amount} ₸*\n"
    f"5. Подтвердите платеж\n"
    f"6. Сохраните чек или сделайте скриншот\n\n"
    f"✅ *После оплаты* нажмите кнопку «Я оплатил» и пришлите чек",
    reply_markup=manual_payment_keyboard(payment["id"]),
    parse_mode="Markdown"
)
    await callback.answer()


@router.callback_query(F.data.startswith("manual_paid:"))
async def manual_payment_paid(callback: CallbackQuery, state: FSMContext, repo: SupabaseRepository, settings: Settings, bot: Bot):
    payment_id = int(callback.data.split(":", 1)[1])
    payment = await repo.get_payment(payment_id)
    if not payment:
        await callback.answer("❌ Платёж не найден", show_alert=True)
        return
    
    await state.update_data(pending_payment_id=payment_id)
    await callback.message.answer(
        "📸 *Пришлите чек об оплате*\n\n"
        "Сделайте скриншот или фото квитанции и отправьте в этот чат.\n\n"
        "После проверки администратор подтвердит оплату.",
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(F.photo)
async def handle_payment_check(message: Message, state: FSMContext, repo: SupabaseRepository, settings: Settings, bot: Bot):
    data = await state.get_data()
    payment_id = data.get("pending_payment_id")
    if not payment_id:
        return
    
    payment = await repo.get_payment(payment_id)
    if not payment:
        await message.answer("❌ Платёж не найден. Попробуйте снова.")
        return
    
    # Отправляем чек админу
    caption = (
        f"🧾 *Новый чек на подтверждение*\n\n"
        f"💰 Сумма: {payment['amount']} ₸\n"
        f"📦 Услуга: {payment['feature']}\n"
        f"👤 Пользователь: {payment['user_id']}\n"
        f"🆔 Платёж #{payment_id}"
    )
    
    await bot.send_photo(
        settings.admin_chat_id,
        message.photo[-1].file_id,
        caption=caption,
        reply_markup=admin_manual_payment_keyboard(payment_id)
    )
    
    await message.answer("✅ Чек отправлен администратору на проверку. Ожидайте подтверждения.")
    await state.update_data(pending_payment_id=None)


@router.callback_query(F.data.startswith("manual_confirm:"))
async def manual_payment_confirm(callback: CallbackQuery, repo: SupabaseRepository, settings: Settings, bot: Bot) -> None:
    payment_id = int(callback.data.split(":", 1)[1])
    payment = await repo.mark_payment_paid(payment_id)
    if not payment:
        await callback.answer("❌ Платёж не найден", show_alert=True)
        return
    
    result = await fulfill_paid_feature(
        repo=repo,
        bot=bot,
        settings=settings,
        user_id=payment["user_id"],
        feature=payment["feature"],
        vacancy_id=payment.get("vacancy_id"),
    )
    await bot.send_message(payment["user_id"], result)
    await callback.message.edit_text(f"✅ Ручная оплата #{payment_id} подтверждена.\n{result}")
    await callback.answer()


@router.callback_query(F.data.startswith("manual_reject:"))
async def manual_payment_reject(callback: CallbackQuery, repo: SupabaseRepository, bot: Bot) -> None:
    payment_id = int(callback.data.split(":", 1)[1])
    payment = await repo.reject_payment(payment_id)
    if payment:
        await bot.send_message(payment["user_id"], "❌ Ручная оплата отклонена администратором.")
    await callback.message.edit_text(f"❌ Ручная оплата #{payment_id} отклонена.")
    await callback.answer()


@router.message(F.text == "👥 Пригласить друга")
@router.message(Command("invite"))
async def invite_friend(message: Message, repo: SupabaseRepository, settings: Settings) -> None:
    referrals_count = await repo.count_referrals(message.from_user.id)
    link = referral_deep_link(settings.bot_username, message.from_user.id)
    await message.answer(
        f"🔗 Ваша ссылка для приглашения:\n`{link}`\n\n"
        f"👥 Приглашено друзей: {referrals_count}\n"
        f"{referral_bonus_text(referrals_count)}",
        parse_mode="Markdown"
    )

@router.message(F.text == "📺 Наш канал")
async def our_channel(message: Message, settings: Settings):
    await message.answer(
        "📢 *Подписывайтесь на наш канал!*\n\n"
        "Там публикуются все свежие вакансии и полезные новости.\n\n"
        "Нажмите на кнопку ниже, чтобы перейти 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="📱 Перейти в канал",
                    url="https://t.me/lisakovsk_job"
                )]
            ]
        )
    )

@router.message(F.text == "📝 Ищу работу")
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

@router.message(F.text == "👤 Личный кабинет")
async def test_lk(message: Message):
    await message.answer("✅ Хендлер поймал текст 'Личный кабинет'")

@router.message(Command("lk"))
async def lk_command(message: Message, repo: SupabaseRepository):
    await my_stats(message, repo)


@router.message(F.text.in_({"👤 Личный кабинет", "/my_stats"}))
async def my_stats(message: Message, repo: SupabaseRepository) -> None:
    try:
        await message.answer("📊 Загружаем статистику...")
        
        user_role = await get_user_role(message.from_user.id, repo)
        role_display = "Работодатель" if user_role == "employer" else "Соискатель" if user_role == "seeker" else "Не определена"
await message.answer(f"👤 Режим: {role_display}")
        
        if user_role == "employer":
            stats = await repo.employer_stats(message.from_user.id)
            text = (
                f"📊 *Статистика работодателя*\n\n"
                f"📌 Всего вакансий: {stats.get('vacancies_total', 0)}\n"
                f"✅ Активные: {stats.get('active_vacancies', 0)}\n"
                f"⏳ На модерации: {stats.get('pending_vacancies', 0)}\n"
                f"🔒 Закрытые: {stats.get('closed_vacancies', 0)}\n"
                f"❌ Отклонённые: {stats.get('rejected_vacancies', 0)}\n\n"
                f"👁️ Просмотров: {stats.get('views', 0)}\n"
                f"📩 Откликов: {stats.get('responses', 0)}\n"
                f"👥 Соискателей в вашей сфере: {stats.get('seekers_in_sphere', 0)}"
            )
            await message.answer(text, parse_mode="Markdown")
        else:
            seeker = await repo.get_seeker(message.from_user.id)
            if not seeker:
                await message.answer(
                    "📝 У вас нет анкеты соискателя.\n\n"
                    "Хотите найти работу? Заполните анкету!\n\n"
                    "👉 Нажмите /resume, чтобы начать"
                )
                return
            stats = await repo.seeker_stats(message.from_user.id)
            text = f"📊 Статистика соискателя:\n\nПросмотров: {stats.get('views', 0)}\nОткликов: {stats.get('responses', 0)}"
            await message.answer(text)
            
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)[:100]}")

@router.message(Command("admin_stats"))
async def admin_stats(message: Message, repo: SupabaseRepository, settings: Settings) -> None:
    if message.chat.id != settings.admin_chat_id:
        await message.answer("⛔ Команда доступна только в админ-чате.")
        return
    await message.answer(admin_stats_text(await repo.admin_stats()))


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

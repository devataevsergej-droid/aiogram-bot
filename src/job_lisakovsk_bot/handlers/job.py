from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, ForceReply, LabeledPrice, Message, PreCheckoutQuery

from job_lisakovsk_bot.config import Settings
from job_lisakovsk_bot.constants import (
    FEATURE_PIN_VACANCY,
    FEATURE_UNLIMITED_VACANCIES,
    FEATURE_URGENT_BROADCAST,
    FEATURE_VIP_SEEKER,
    PAYMENT_TYPE_MANUAL,
    PAYMENT_TYPE_STARS,
)
from job_lisakovsk_bot.db import SupabaseRepository
from job_lisakovsk_bot.keyboards.job_inline import (
    admin_manual_payment_keyboard,
    buy_unlimited_keyboard,
    feedback_keyboard,
    main_menu,
    manual_payment_keyboard,
    moderation_keyboard,
    schedules_keyboard,
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
from job_lisakovsk_bot.services.limits import can_create_vacancy, can_send_notification, has_free_monthly_urgent, has_free_vip_bonus
from job_lisakovsk_bot.services.payments import build_payment_payload, get_feature_request, parse_payment_payload
from job_lisakovsk_bot.services.referrals import parse_referral_arg, referral_bonus_text, referral_deep_link
from job_lisakovsk_bot.services.salary import parse_salary_range

router = Router(name="job")


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
        return "Безлимит вакансий активирован на месяц."

    if feature == FEATURE_VIP_SEEKER:
        await repo.activate_vip(user_id)
        return "VIP-статус соискателя активирован на месяц."

    if vacancy_id is None:
        return "Оплата получена, но вакансия не указана. Напишите администратору."

    vacancy = await repo.get_vacancy(vacancy_id)
    if not vacancy:
        return "Оплата получена, но вакансия не найдена. Напишите администратору."

    if feature == FEATURE_PIN_VACANCY:
        if not vacancy.get("channel_message_id"):
            return "Оплата получена, но вакансия ещё не опубликована в канале."
        await bot.pin_chat_message(settings.channel_id, vacancy["channel_message_id"], disable_notification=True)
        await repo.schedule_unpin(vacancy_id, vacancy["channel_message_id"], datetime.now(UTC) + timedelta(days=3))
        return "Вакансия закреплена в канале на 3 дня."

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
        return f"Срочная рассылка выполнена. Отправлено уведомлений: {sent}."

    return "Оплата получена."


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, command: CommandObject, repo: SupabaseRepository) -> None:
    arg = command.args
    referrer_id = parse_referral_arg(arg)
    if referrer_id is not None:
        await repo.register_referral(referrer_id, message.from_user.id)
        await message.answer("Реферальная ссылка учтена. Добро пожаловать в «Работа Лисаковск»!", reply_markup=main_menu())
        return
    if arg == "resume":
        await seeker_start(message, state)
        return
    if arg == "vacancy":
        await vacancy_start(message, state)
        return

    await message.answer(
        "Привет! Это бот «Работа Лисаковск». Выберите, что хотите сделать:",
        reply_markup=main_menu(),
    )


@router.message(F.text == "Ищу работу")
async def seeker_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(SeekerForm.sphere)
    await message.answer("Выберите сферу:", reply_markup=spheres_keyboard("seeker_sphere"))


@router.callback_query(SeekerForm.sphere, F.data.startswith("seeker_sphere:"))
async def seeker_sphere(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(sphere=callback.data.split(":", 1)[1])
    await state.set_state(SeekerForm.schedule)
    await callback.message.edit_text("Выберите график:", reply_markup=schedules_keyboard("seeker_schedule"))
    await callback.answer()


@router.callback_query(SeekerForm.schedule, F.data.startswith("seeker_schedule:"))
async def seeker_schedule(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(schedule=callback.data.split(":", 1)[1])
    await state.set_state(SeekerForm.salary)
    await callback.message.edit_text(
        "Укажите зарплату от и до, например: 200000-300000. Если не важно — напишите «Не важно»."
    )
    await callback.answer()


@router.message(SeekerForm.salary)
async def seeker_salary(message: Message, state: FSMContext) -> None:
    try:
        salary_min, salary_max = parse_salary_range(message.text or "")
    except ValueError:
        await message.answer("Не понял сумму. Напишите диапазон вроде 200000-300000 или «Не важно».")
        return

    await state.update_data(salary_min=salary_min, salary_max=salary_max)
    await state.set_state(SeekerForm.about)
    await message.answer("Коротко о себе одним предложением. Например: «Сварщик с опытом 5 лет, есть свой инструмент».")


@router.message(SeekerForm.about)
async def seeker_about(message: Message, state: FSMContext, repo: SupabaseRepository) -> None:
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
        "Ты в базе. Когда появится подходящая вакансия — я пришлю уведомление. "
        "Пока можешь посмотреть открытые вакансии.",
        reply_markup=main_menu(),
    )


@router.message(F.text.in_({"Смотреть вакансии", "/vacancies"}))
async def show_vacancies(message: Message, repo: SupabaseRepository, settings: Settings) -> None:
    seeker = await repo.get_seeker(message.from_user.id)
    vacancies = await repo.list_active_vacancies(sphere=seeker["sphere"] if seeker else None)
    if not vacancies:
        await message.answer("Пока активных вакансий нет. Как только появятся — пришлю уведомление.")
        return

    for vacancy in vacancies:
        await message.answer(
            vacancy_private_text(vacancy, settings.bot_username),
            reply_markup=vacancies_keyboard(vacancy["id"]),
        )


@router.message(F.text == "Ищу сотрудника")
@router.message(F.text == "Разместить вакансию")
async def vacancy_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(VacancyForm.title)
    await message.answer("Кого ищете? Напишите должность или услугу. Например: «сварщик» или «бариста».")


@router.message(VacancyForm.title)
async def vacancy_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=(message.text or "").strip())
    await state.set_state(VacancyForm.sphere)
    await message.answer("Выберите сферу:", reply_markup=spheres_keyboard("vacancy_sphere"))


@router.callback_query(VacancyForm.sphere, F.data.startswith("vacancy_sphere:"))
async def vacancy_sphere(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(sphere=callback.data.split(":", 1)[1])
    await state.set_state(VacancyForm.schedule)
    await callback.message.edit_text("Выберите график:", reply_markup=schedules_keyboard("vacancy_schedule"))
    await callback.answer()


@router.callback_query(VacancyForm.schedule, F.data.startswith("vacancy_schedule:"))
async def vacancy_schedule(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(schedule=callback.data.split(":", 1)[1])
    await state.set_state(VacancyForm.salary)
    await callback.message.edit_text("Укажите зарплату от и до, например: 250000-300000.")
    await callback.answer()


@router.message(VacancyForm.salary)
async def vacancy_salary(message: Message, state: FSMContext) -> None:
    try:
        salary_min, salary_max = parse_salary_range(message.text or "")
    except ValueError:
        await message.answer("Не понял сумму. Напишите диапазон вроде 250000-300000.")
        return
    await state.update_data(salary_min=salary_min, salary_max=salary_max)
    await state.set_state(VacancyForm.contacts)
    await message.answer("Оставьте контакты: телефон или @username.")


@router.message(VacancyForm.contacts)
async def vacancy_contacts(message: Message, state: FSMContext) -> None:
    await state.update_data(contacts=(message.text or "").strip())
    await state.set_state(VacancyForm.description)
    await message.answer("Опишите, что требуется от кандидата.")


@router.message(VacancyForm.description)
async def vacancy_description(
    message: Message,
    state: FSMContext,
    repo: SupabaseRepository,
    settings: Settings,
    bot: Bot,
) -> None:
    usage = await repo.get_or_create_usage(message.from_user.id)
    referrals = await repo.count_referrals(message.from_user.id)
    has_unlimited = await repo.has_unlimited_vacancies(message.from_user.id)
    decision = can_create_vacancy(int(usage.get("vacancies_this_month") or 0), referrals, has_unlimited)
    if not decision.allowed:
        await message.answer(
            f"Бесплатный лимит вакансий на месяц исчерпан ({decision.used}/{decision.limit}). "
            "Можно купить безлимит или пригласить друга.",
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
    await message.answer("Вакансия отправлена на модерацию. После проверки я сообщу результат.", reply_markup=main_menu())
    await bot.send_message(
        settings.admin_chat_id,
        "Новая вакансия на модерацию:\n\n" + vacancy_public_text(vacancy, settings.bot_username),
        reply_markup=moderation_keyboard(vacancy["id"]),
    )


@router.callback_query(F.data.startswith("moderate_approve:"))
async def approve_vacancy(callback: CallbackQuery, repo: SupabaseRepository, settings: Settings, bot: Bot) -> None:
    vacancy_id = int(callback.data.split(":", 1)[1])
    vacancy = await repo.get_vacancy(vacancy_id)
    if not vacancy:
        await callback.answer("Вакансия не найдена", show_alert=True)
        return

    channel_message = await bot.send_message(settings.channel_id, vacancy_public_text(vacancy, settings.bot_username))
    vacancy = await repo.approve_vacancy(vacancy_id, channel_message.message_id)
    await bot.send_message(
        vacancy["employer_id"],
        "Ваша вакансия одобрена и опубликована в канале. Хотите ускорить поиск?",
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
        f"Напишите причину отклонения вакансии #{vacancy_id} одним сообщением.",
        reply_markup=ForceReply(selective=True),
    )
    await callback.answer()


@router.message(RejectVacancyForm.reason)
async def reject_vacancy_reason(message: Message, state: FSMContext, repo: SupabaseRepository, bot: Bot) -> None:
    data = await state.get_data()
    vacancy_id = int(data["reject_vacancy_id"])
    reason = (message.text or "Не прошла модерацию").strip()
    vacancy = await repo.reject_vacancy(vacancy_id, reason)
    await bot.send_message(vacancy["employer_id"], f"Вакансия отклонена модератором. Причина: {reason}")
    await message.answer(f"❌ Вакансия #{vacancy_id} отклонена. Причина отправлена работодателю.")
    await state.clear()


@router.callback_query(F.data.startswith("vacancy_like:"))
async def vacancy_like(callback: CallbackQuery, repo: SupabaseRepository, bot: Bot) -> None:
    vacancy_id = int(callback.data.split(":", 1)[1])
    vacancy = await repo.get_vacancy(vacancy_id)
    seeker = await repo.get_seeker(callback.from_user.id)
    if not vacancy or not seeker:
        await callback.answer("Сначала заполните анкету соискателя.", show_alert=True)
        return

    await repo.set_reaction(vacancy_id, callback.from_user.id, "like")
    contact = f"@{callback.from_user.username}" if callback.from_user.username else f"telegram id {callback.from_user.id}"
    await bot.send_message(
        vacancy["employer_id"],
        f"На вашу вакансию откликнулся соискатель #{callback.from_user.id}:\n\n"
        f"{seeker_card(seeker)}\n\nКонтакты: {contact}",
    )
    await callback.answer("Отклик отправлен работодателю.", show_alert=True)


@router.callback_query(F.data.startswith("vacancy_dislike:"))
async def vacancy_dislike(callback: CallbackQuery, repo: SupabaseRepository) -> None:
    vacancy_id = int(callback.data.split(":", 1)[1])
    await repo.set_reaction(vacancy_id, callback.from_user.id, "dislike")
    await callback.message.delete()
    await callback.answer("Скрыто")


@router.callback_query(F.data.startswith("vacancy_complain:"))
async def vacancy_complain(callback: CallbackQuery, repo: SupabaseRepository, settings: Settings, bot: Bot) -> None:
    vacancy_id = int(callback.data.split(":", 1)[1])
    await repo.set_reaction(vacancy_id, callback.from_user.id, "complaint")
    await bot.send_message(settings.admin_chat_id, f"Жалоба на вакансию #{vacancy_id} от пользователя {callback.from_user.id}")
    await callback.answer("Жалоба отправлена модератору.", show_alert=True)


@router.callback_query(F.data.startswith("buy:"))
async def buy_feature(callback: CallbackQuery, repo: SupabaseRepository, settings: Settings, bot: Bot) -> None:
    _, feature, *rest = callback.data.split(":")
    vacancy_id = int(rest[0]) if rest else None
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
            await callback.message.answer("Использован реферальный бонус: " + result)
            await callback.answer()
            return
    if feature == FEATURE_VIP_SEEKER and has_free_vip_bonus(referrals):
        if await repo.referral_vip_bonus_available(callback.from_user.id, referrals):
            await repo.activate_vip(callback.from_user.id)
            await repo.mark_referral_vip_bonus_used(callback.from_user.id)
            await callback.message.answer("Использован реферальный бонус: VIP-статус активирован на месяц.")
            await callback.answer()
            return
    request = get_feature_request(feature, vacancy_id)
    await callback.message.answer_invoice(
        title=request.title,
        description=f"Оплата функции «{request.title}» для бота Работа Лисаковск",
        payload=build_payment_payload(feature, vacancy_id),
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=request.title, amount=request.amount)],
    )
    await callback.answer()


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
        f"Переведите {request.amount} Stars-эквивалент на баланс Билайн {settings.beeline_payment_phone}.\n"
        "После перевода нажмите «Я оплатил». Админ проверит оплату вручную.",
        reply_markup=manual_payment_keyboard(payment["id"]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("manual_paid:"))
async def manual_payment_paid(callback: CallbackQuery, repo: SupabaseRepository, settings: Settings, bot: Bot) -> None:
    payment_id = int(callback.data.split(":", 1)[1])
    payment = await repo.get_payment(payment_id)
    if not payment:
        await callback.answer("Платёж не найден", show_alert=True)
        return
    await bot.send_message(
        settings.admin_chat_id,
        f"Пользователь {callback.from_user.id} сообщил о ручной оплате #{payment_id}: "
        f"{payment['feature']} на сумму {payment['amount']}.",
        reply_markup=admin_manual_payment_keyboard(payment_id),
    )
    await callback.answer("Заявка отправлена админу на проверку.", show_alert=True)


@router.callback_query(F.data.startswith("manual_confirm:"))
async def manual_payment_confirm(callback: CallbackQuery, repo: SupabaseRepository, settings: Settings, bot: Bot) -> None:
    payment_id = int(callback.data.split(":", 1)[1])
    payment = await repo.mark_payment_paid(payment_id)
    result = await fulfill_paid_feature(
        repo=repo,
        bot=bot,
        settings=settings,
        user_id=payment["user_id"],
        feature=payment["feature"],
        vacancy_id=payment.get("vacancy_id"),
    )
    await bot.send_message(payment["user_id"], result)
    await callback.message.edit_text(f"✅ Ручная оплата #{payment_id} подтверждена. {result}")
    await callback.answer()


@router.callback_query(F.data.startswith("manual_reject:"))
async def manual_payment_reject(callback: CallbackQuery, repo: SupabaseRepository, bot: Bot) -> None:
    payment_id = int(callback.data.split(":", 1)[1])
    payment = await repo.reject_payment(payment_id)
    if payment:
        await bot.send_message(payment["user_id"], "Ручная оплата отклонена администратором.")
    await callback.message.edit_text(f"❌ Ручная оплата #{payment_id} отклонена.")
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    try:
        parse_payment_payload(pre_checkout_query.invoice_payload)
    except ValueError:
        await pre_checkout_query.answer(ok=False, error_message="Неизвестный платёж")
        return
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message, repo: SupabaseRepository, settings: Settings, bot: Bot) -> None:
    payment_info = message.successful_payment
    feature, vacancy_id = parse_payment_payload(payment_info.invoice_payload)
    payment = await repo.create_payment(
        user_id=message.from_user.id,
        payment_type=PAYMENT_TYPE_STARS,
        amount=payment_info.total_amount,
        feature=feature,
        vacancy_id=vacancy_id,
        status="paid",
    )
    await repo.mark_payment_paid(
        payment["id"],
        telegram_payment_charge_id=payment_info.telegram_payment_charge_id,
        provider_payment_charge_id=payment_info.provider_payment_charge_id,
    )
    result = await fulfill_paid_feature(
        repo=repo,
        bot=bot,
        settings=settings,
        user_id=message.from_user.id,
        feature=feature,
        vacancy_id=vacancy_id,
    )
    await message.answer(result, reply_markup=main_menu())


@router.message(F.text == "Пригласить друга")
@router.message(Command("invite"))
async def invite_friend(message: Message, repo: SupabaseRepository, settings: Settings) -> None:
    referrals_count = await repo.count_referrals(message.from_user.id)
    link = referral_deep_link(settings.bot_username, message.from_user.id)
    await message.answer(
        f"Ваша ссылка для приглашения:\n{link}\n\n"
        f"Приглашено друзей: {referrals_count}\n"
        f"{referral_bonus_text(referrals_count)}"
    )


@router.message(F.text == "Наши проекты")
async def projects(message: Message, settings: Settings) -> None:
    await message.answer(
        "Наши проекты:\n"
        f"🔮 Оракул: {settings.project_oracle_url}\n"
        f"⭐ Рейтинг: {settings.project_rating_url}\n"
        f"🛠 Мастерская: {settings.project_workshop_url}"
    )


@router.message(F.text.in_({"Личный кабинет", "/my_stats"}))
async def my_stats(message: Message, repo: SupabaseRepository) -> None:
    seeker = await repo.get_seeker(message.from_user.id)
    latest_vacancy = await repo.get_latest_approved_vacancy(message.from_user.id)
    if latest_vacancy:
        stats = await repo.employer_stats(message.from_user.id)
        text = employer_stats_text(stats)
    else:
        stats = await repo.seeker_stats(message.from_user.id)
        text = seeker_stats_text(stats)
        if not seeker:
            text += "\n\nЧтобы включить статистику соискателя, заполните анкету."
    await message.answer(text, reply_markup=feedback_keyboard(latest_vacancy["id"] if latest_vacancy else None))


@router.message(Command("admin_stats"))
async def admin_stats(message: Message, repo: SupabaseRepository, settings: Settings) -> None:
    if message.chat.id != settings.admin_chat_id:
        await message.answer("Команда доступна только в админ-чате.")
        return
    await message.answer(admin_stats_text(await repo.admin_stats()))


@router.callback_query(F.data == "found_work")
async def found_work(callback: CallbackQuery, repo: SupabaseRepository) -> None:
    await repo.mark_seeker_found_work(callback.from_user.id)
    await callback.answer("Поздравляю! Анкета отмечена как закрытая.", show_alert=True)


@router.callback_query(F.data.startswith("close_vacancy:"))
async def close_vacancy(callback: CallbackQuery, repo: SupabaseRepository) -> None:
    vacancy_id = int(callback.data.split(":", 1)[1])
    vacancy = await repo.close_vacancy(vacancy_id, callback.from_user.id)
    if not vacancy:
        await callback.answer("Вакансия не найдена", show_alert=True)
        return
    await callback.answer("Вакансия отмечена как закрытая.", show_alert=True)

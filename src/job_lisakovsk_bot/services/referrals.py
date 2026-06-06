from __future__ import annotations


def referral_deep_link(bot_username: str, user_id: int) -> str:
    return f"https://t.me/{bot_username}?start=ref_{user_id}"


def parse_referral_arg(arg: str | None) -> int | None:
    if not arg:
        return None

    if "_r" in arg:
        raw_id = arg.split("_r", 1)[1]
    elif arg.startswith("ref_"):
        raw_id = arg.removeprefix("ref_")
    else:
        return None

    if not raw_id.isdigit():
        return None

    return int(raw_id)


def referral_bonus_text(
    referrals_count: int
) -> str:

    progress = []

    if referrals_count >= 1:
        progress.append(
            "✅ 1 приглашённый → бесплатное поднятие анкеты"
        )

    if referrals_count >= 3:
        progress.append(
            "✅ 3 приглашённых → 5 уведомлений в день"
        )

    if referrals_count >= 5:
        progress.append(
            "✅ 5 приглашённых → 1 бесплатная срочная рассылка в месяц"
        )

    if referrals_count >= 10:
        progress.append(
            "✅ 10 приглашённых → VIP на 30 дней"
        )

    return (
        "🎁 Реферальные бонусы\n\n"

        f"👥 Приглашено: {referrals_count}\n\n"

        "Как начисляются рефералы:\n"
        "• Соискатель должен заполнить анкету\n"
        "• Работодатель должен разместить вакансию\n\n"

        "Доступные бонусы:\n"
        f"{chr(10).join(progress) if progress else 'Пока бонусов нет'}\n\n"

        "Следующие цели:\n"
        f"{'🎯 Пригласите 1 пользователя для первого бонуса' if referrals_count < 1 else ''}"
        f"{'🎯 3 приглашённых → 5 уведомлений в день' if referrals_count < 3 else ''}"
        f"{'🎯 5 приглашённых → бесплатная срочная рассылка' if 3 <= referrals_count < 5 else ''}"
        f"{'🎯 10 приглашённых → VIP на 30 дней' if 5 <= referrals_count < 10 else ''}"
    )


def has_free_vip_bonus(referrals_count: int) -> bool:
    """Проверяет, положен ли бесплатный VIP за 10 рефералов"""
    return referrals_count >= 10


def has_free_monthly_urgent(referrals_count: int, urgent_used_this_month: int) -> bool:
    """Проверяет, можно ли использовать бесплатную срочную рассылку (1 раз в месяц за 5 рефералов)"""
    return referrals_count >= 5 and urgent_used_this_month < 1

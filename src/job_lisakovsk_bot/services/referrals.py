from __future__ import annotations


def referral_deep_link(bot_username: str, user_id: int) -> str:
    return f"https://t.me/{bot_username}?start=ref_{user_id}"


def parse_referral_arg(arg: str | None) -> int | None:
    if not arg or not arg.startswith("ref_"):
        return None
    raw_id = arg.removeprefix("ref_")
    if not raw_id.isdigit():
        return None
    return int(raw_id)


def referral_bonus_text(referrals_count: int) -> str:
    bonuses = []
    if referrals_count >= 1:
        bonuses.append("+1 бесплатная вакансия в месяц")
    if referrals_count >= 3:
        bonuses.append("до 5 уведомлений в день")
    if referrals_count >= 5:
        bonuses.append("1 срочная рассылка бесплатно в месяц")
    if referrals_count >= 10:
        bonuses.append("VIP на месяц бесплатно")
    if not bonuses:
        return "Пока бонусов нет. Пригласи 1 друга, чтобы получить +1 бесплатную вакансию в месяц."
    return "Доступные бонусы:\n- " + "\n- ".join(bonuses)


def has_free_vip_bonus(referrals_count: int) -> bool:
    """Проверяет, положен ли бесплатный VIP за 10 рефералов"""
    return referrals_count >= 10


def has_free_monthly_urgent(referrals_count: int, urgent_used_this_month: int) -> bool:
    """Проверяет, можно ли использовать бесплатную срочную рассылку (1 раз в месяц за 5 рефералов)"""
    return referrals_count >= 5 and urgent_used_this_month < 1

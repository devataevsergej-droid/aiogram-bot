from __future__ import annotations

from dataclasses import dataclass
from datetime import date

FREE_VACANCIES_PER_MONTH = 1
FREE_NOTIFICATIONS_PER_DAY = 3
REFERRAL_NOTIFICATION_BONUS_THRESHOLD = 3
REFERRAL_NOTIFICATION_BONUS_LIMIT = 5
REFERRAL_EXTRA_VACANCY_THRESHOLD = 1
REFERRAL_FREE_URGENT_THRESHOLD = 5
REFERRAL_FREE_VIP_THRESHOLD = 10


@dataclass(frozen=True)
class UsageDecision:
    allowed: bool
    limit: int
    used: int
    reason: str | None = None


def month_key(today: date | None = None) -> str:
    current = today or date.today()
    return current.strftime("%Y-%m")


def day_key(today: date | None = None) -> str:
    current = today or date.today()
    return current.isoformat()


def free_vacancy_limit(referrals_count: int) -> int:
    bonus = 1 if referrals_count >= REFERRAL_EXTRA_VACANCY_THRESHOLD else 0
    return FREE_VACANCIES_PER_MONTH + bonus


def notification_limit(referrals_count: int) -> int:
    if referrals_count >= REFERRAL_NOTIFICATION_BONUS_THRESHOLD:
        return REFERRAL_NOTIFICATION_BONUS_LIMIT
    return FREE_NOTIFICATIONS_PER_DAY


def can_create_vacancy(used: int, referrals_count: int, has_unlimited: bool) -> UsageDecision:
    limit = free_vacancy_limit(referrals_count)
    if has_unlimited or used < limit:
        return UsageDecision(True, limit, used)
    return UsageDecision(False, limit, used, "free_vacancy_limit_reached")


def can_send_notification(used: int, referrals_count: int, has_unlimited: bool = False) -> UsageDecision:
    limit = notification_limit(referrals_count)
    if has_unlimited or used < limit:
        return UsageDecision(True, limit, used)
    return UsageDecision(False, limit, used, "daily_notification_limit_reached")


def has_free_monthly_urgent(referrals_count: int, urgent_used_this_month: int) -> bool:
    return referrals_count >= REFERRAL_FREE_URGENT_THRESHOLD and urgent_used_this_month < 1


def has_free_vip_bonus(referrals_count: int) -> bool:
    return referrals_count >= REFERRAL_FREE_VIP_THRESHOLD

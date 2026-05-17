from job_lisakovsk_bot.services.limits import (
    can_create_vacancy,
    can_send_notification,
    free_vacancy_limit,
    has_free_monthly_urgent,
    has_free_vip_bonus,
    notification_limit,
)


def test_free_vacancy_limit_includes_referral_bonus():
    assert free_vacancy_limit(0) == 1
    assert free_vacancy_limit(1) == 2


def test_can_create_vacancy_blocks_without_unlimited():
    decision = can_create_vacancy(used=1, referrals_count=0, has_unlimited=False)
    assert not decision.allowed
    assert decision.reason == "free_vacancy_limit_reached"


def test_can_create_vacancy_allows_unlimited():
    assert can_create_vacancy(used=20, referrals_count=0, has_unlimited=True).allowed


def test_notification_limit_referral_bonus():
    assert notification_limit(0) == 3
    assert notification_limit(3) == 5
    assert can_send_notification(used=4, referrals_count=3).allowed
    assert not can_send_notification(used=5, referrals_count=3).allowed


def test_referral_threshold_bonuses():
    assert has_free_monthly_urgent(5, 0)
    assert not has_free_monthly_urgent(5, 1)
    assert has_free_vip_bonus(10)

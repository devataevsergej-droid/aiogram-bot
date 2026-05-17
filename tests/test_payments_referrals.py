import pytest

from job_lisakovsk_bot.constants import FEATURE_PIN_VACANCY, FEATURE_PRICES_STARS, FEATURE_VIP_SEEKER
from job_lisakovsk_bot.services.payments import build_payment_payload, get_feature_request, parse_payment_payload
from job_lisakovsk_bot.services.referrals import parse_referral_arg, referral_bonus_text, referral_deep_link


def test_payment_payload_roundtrip_with_vacancy():
    payload = build_payment_payload(FEATURE_PIN_VACANCY, 42)
    assert parse_payment_payload(payload) == (FEATURE_PIN_VACANCY, 42)


def test_payment_payload_rejects_unknown_feature():
    with pytest.raises(ValueError):
        parse_payment_payload("joblis:unknown")


def test_feature_request_uses_stars_price():
    request = get_feature_request(FEATURE_VIP_SEEKER)
    assert request.amount == FEATURE_PRICES_STARS[FEATURE_VIP_SEEKER]
    assert "VIP" in request.title


def test_referral_link_and_arg_parser():
    assert referral_deep_link("JobLis_bot", 123) == "https://t.me/JobLis_bot?start=ref_123"
    assert parse_referral_arg("ref_123") == 123
    assert parse_referral_arg("resume") is None


def test_referral_bonus_text_lists_unlocked_bonuses():
    text = referral_bonus_text(5)
    assert "+1 бесплатная вакансия" in text
    assert "до 5 уведомлений" in text
    assert "срочная рассылка" in text

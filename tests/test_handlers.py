import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("aiogram")

from job_lisakovsk_bot.constants import FEATURE_PIN_VACANCY, FEATURE_URGENT_BROADCAST
from job_lisakovsk_bot.handlers.job import fulfill_paid_feature, reject_vacancy_reason, send_vacancy_notifications


class FakeRepo:
    def __init__(self):
        self.notifications = []
        self.increments = []
        self.unpins = []
        self.rejected = None
        self.usage = {}
        self.referrals = {}

    async def get_or_create_usage(self, user_id):
        return self.usage.get(user_id, {"notifications_today": 0})

    async def count_referrals(self, user_id):
        return self.referrals.get(user_id, 0)

    async def record_notification(self, vacancy_id, seeker_id):
        self.notifications.append((vacancy_id, seeker_id))

    async def increment_notifications_today(self, user_id):
        self.increments.append(user_id)

    async def get_vacancy(self, vacancy_id):
        return {"id": vacancy_id, "channel_message_id": 99, "title": "сварщик", "schedule": "Полный день", "salary_min": None, "salary_max": None, "description": "Опыт", "contacts": "@hr"}

    async def schedule_unpin(self, vacancy_id, channel_message_id, unpin_at):
        self.unpins.append((vacancy_id, channel_message_id, unpin_at))

    async def reject_vacancy(self, vacancy_id, reason):
        self.rejected = (vacancy_id, reason)
        return {"id": vacancy_id, "employer_id": 777}


class FakeBot:
    def __init__(self):
        self.messages = []
        self.pins = []

    async def send_message(self, chat_id, text, reply_markup=None):
        self.messages.append((chat_id, text, reply_markup))

    async def pin_chat_message(self, chat_id, message_id, disable_notification=False):
        self.pins.append((chat_id, message_id, disable_notification))


class FakeState:
    async def get_data(self):
        return {"reject_vacancy_id": 42}

    async def clear(self):
        self.cleared = True


class FakeMessage:
    text = "Подозрительные условия"

    def __init__(self):
        self.answers = []

    async def answer(self, text, reply_markup=None):
        self.answers.append((text, reply_markup))


def test_send_vacancy_notifications_respects_daily_limit():
    repo = FakeRepo()
    repo.usage = {1: {"notifications_today": 3}, 2: {"notifications_today": 0}}
    bot = FakeBot()
    settings = SimpleNamespace(bot_username="JobLis_bot")
    vacancy = {"id": 5, "title": "сварщик", "schedule": "Полный день", "salary_min": None, "salary_max": None, "description": "Опыт", "contacts": "@hr"}

    sent = asyncio.run(
        send_vacancy_notifications(
            repo=repo,
            bot=bot,
            settings=settings,
            vacancy=vacancy,
            seekers=[{"user_id": 1}, {"user_id": 2}],
        )
    )

    assert sent == 1
    assert repo.notifications == [(5, 2)]


def test_fulfill_paid_pin_schedules_unpin():
    repo = FakeRepo()
    bot = FakeBot()
    settings = SimpleNamespace(channel_id=-100, bot_username="JobLis_bot")

    result = asyncio.run(
        fulfill_paid_feature(
            repo=repo,
            bot=bot,
            settings=settings,
            user_id=1,
            feature=FEATURE_PIN_VACANCY,
            vacancy_id=42,
        )
    )

    assert "закреплена" in result
    assert bot.pins == [(-100, 99, True)]
    assert repo.unpins[0][:2] == (42, 99)


def test_reject_vacancy_reason_saves_and_notifies():
    repo = FakeRepo()
    bot = FakeBot()
    message = FakeMessage()

    asyncio.run(reject_vacancy_reason(message, FakeState(), repo, bot))

    assert repo.rejected == (42, "Подозрительные условия")
    assert bot.messages[0][0] == 777
    assert "Подозрительные условия" in bot.messages[0][1]
    assert "отклонена" in message.answers[0][0]

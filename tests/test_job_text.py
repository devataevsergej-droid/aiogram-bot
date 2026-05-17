from job_lisakovsk_bot.services.job_text import format_salary, vacancy_public_text


def test_format_salary_ranges():
    assert format_salary(250000, 300000) == "250 000 – 300 000 тг"
    assert format_salary(200000, None) == "от 200 000 тг"
    assert format_salary(None, 180000) == "до 180 000 тг"
    assert format_salary(None, None) == "Не важно"


def test_vacancy_public_text_contains_lisakovsk_and_bot_link():
    text = vacancy_public_text(
        {
            "title": "сварщик",
            "salary_min": 250000,
            "salary_max": 300000,
            "schedule": "Полный день",
            "description": "Опыт от 3 лет, свой инструмент.",
            "contacts": "@rabotodatel_123",
        },
        "JobLis_bot",
    )

    assert "🏗 Требуется сварщик" in text
    assert "📍 Лисаковск, полный день" in text
    assert "Разместить свою вакансию: @JobLis_bot" in text

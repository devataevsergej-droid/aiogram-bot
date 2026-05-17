from job_lisakovsk_bot.services.salary import parse_salary_range


def test_parse_salary_range():
    assert parse_salary_range("250000-300000") == (250000, 300000)
    assert parse_salary_range("300 000 – 250 000") == (250000, 300000)
    assert parse_salary_range("Не важно") == (None, None)
    assert parse_salary_range("от 200000") == (200000, None)

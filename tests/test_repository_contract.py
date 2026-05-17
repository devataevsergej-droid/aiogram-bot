from pathlib import Path


def test_paid_feature_checks_use_expires_at_not_created_at_window():
    source = Path("src/job_lisakovsk_bot/db.py").read_text()
    assert '"expires_at": (now + timedelta(days=31)).isoformat()' in source
    assert '.gt("expires_at", now)' in source
    assert '.gte("created_at", since)' not in source[source.index("async def has_active_paid_feature") : source.index("async def has_unlimited_vacancies")]


def test_weekly_stats_builds_top_employers_from_likes():
    source = Path("src/job_lisakovsk_bot/db.py").read_text()
    weekly = source[source.index("async def weekly_stats") :]
    assert '.eq("reacted", "like")' in weekly
    assert "employer_like_counts" in weekly
    assert "вакансий" in weekly
    assert "откликов" in weekly

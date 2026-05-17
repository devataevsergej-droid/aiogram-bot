from pathlib import Path


def test_schema_contains_monetization_and_limits_tables():
    schema = Path("db/schema.sql").read_text()
    assert "create table if not exists payments" in schema
    assert "create table if not exists usage_limits" in schema
    assert "create table if not exists referrals" in schema
    assert "create table if not exists scheduled_unpins" in schema


def test_schema_extends_existing_tables_without_replacing_them():
    schema = Path("db/schema.sql").read_text()
    assert "create table if not exists job_seekers" in schema
    assert "create table if not exists job_vacancies" in schema
    assert "alter table job_seekers add column if not exists referred_by" in schema
    assert "alter table job_vacancies add column if not exists closed_via_bot" in schema

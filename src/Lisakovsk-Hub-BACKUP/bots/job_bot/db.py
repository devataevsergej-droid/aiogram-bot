from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from supabase import Client, create_client

from constants import (
    FEATURE_PIN_VACANCY,
    FEATURE_UNLIMITED_VACANCIES,
    FEATURE_VIP_SEEKER,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_PENDING,
    VACANCY_STATUS_APPROVED,
    VACANCY_STATUS_CLOSED,
    VACANCY_STATUS_REJECTED,
)
from services.limits import day_key, month_key


class SupabaseRepository:
    def __init__(self, url: str, key: str) -> None:
        self.client: Client = create_client(url, key)

    async def _run(self, fn, *args, **kwargs):
        return await asyncio.to_thread(fn, *args, **kwargs)

    async def upsert_seeker(self, payload: dict[str, Any]) -> dict[str, Any]:
        def query():
            return self.client.table("job_seekers").upsert(payload, on_conflict="user_id").execute()
        result = await self._run(query)
        return result.data[0]

    async def get_seeker(self, user_id: int) -> dict[str, Any] | None:
        def query():
            return self.client.table("job_seekers").select("*").eq("user_id", user_id).maybe_single().execute()
        result = await self._run(query)
        if not result or not result.data:
            return None
        return result.data

    async def create_vacancy(self, payload: dict[str, Any]) -> dict[str, Any]:
        def query():
            return self.client.table("job_vacancies").insert(payload).execute()
        result = await self._run(query)
        return result.data[0]

    async def get_vacancy(self, vacancy_id: int) -> dict[str, Any] | None:
        def query():
            return self.client.table("job_vacancies").select("*").eq("id", vacancy_id).maybe_single().execute()
        result = await self._run(query)
        if not result or not result.data:
            return None
        return result.data

    async def get_latest_approved_vacancy(self, employer_id: int) -> dict[str, Any] | None:
        def query():
            return (
                self.client.table("job_vacancies")
                .select("*")
                .eq("employer_id", employer_id)
                .eq("status", VACANCY_STATUS_APPROVED)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
        result = await self._run(query)
        if not result or not result.data:
            return None
        return result.data[0]

    async def approve_vacancy(self, vacancy_id: int, channel_message_id: int | None = None) -> dict[str, Any] | None:
        payload: dict[str, Any] = {"status": VACANCY_STATUS_APPROVED}
        if channel_message_id is not None:
            payload["channel_message_id"] = channel_message_id

        def query():
            return self.client.table("job_vacancies").update(payload).eq("id", vacancy_id).execute()
        result = await self._run(query)
        if not result or not result.data:
            return None
        return result.data[0]

    async def reject_vacancy(self, vacancy_id: int, reason: str = "Не прошла модерацию") -> dict[str, Any] | None:
        def query():
            return (
                self.client.table("job_vacancies")
                .update({"status": VACANCY_STATUS_REJECTED, "moderation_reason": reason})
                .eq("id", vacancy_id)
                .execute()
            )
        result = await self._run(query)
        if not result or not result.data:
            return None
        return result.data[0]

    async def close_vacancy(self, vacancy_id: int, employer_id: int | None = None) -> dict[str, Any] | None:
        def query():
            request = self.client.table("job_vacancies").update(
                {"status": VACANCY_STATUS_CLOSED, "closed_via_bot": True}
            ).eq("id", vacancy_id)
            if employer_id is not None:
                request = request.eq("employer_id", employer_id)
            return request.execute()
        result = await self._run(query)
        if not result or not result.data:
            return None
        return result.data[0]

    async def mark_seeker_found_work(self, user_id: int) -> dict[str, Any] | None:
        def query():
            return (
                self.client.table("job_seekers")
                .update({"active": False, "found_work": True})
                .eq("user_id", user_id)
                .execute()
            )
        result = await self._run(query)
        if not result or not result.data:
            return None
        return result.data[0]

    async def list_active_vacancies(self, sphere: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        def query():
            request = (
                self.client.table("job_vacancies")
                .select("*")
                .eq("status", VACANCY_STATUS_APPROVED)
                .order("created_at", desc=True)
                .limit(limit)
            )
            if sphere:
                request = request.eq("sphere", sphere)
            return request.execute()
        result = await self._run(query)
        return result.data

    async def find_matching_seekers(self, vacancy: dict[str, Any]) -> list[dict[str, Any]]:
        def query():
            return (
                self.client.table("job_seekers")
                .select("*")
                .eq("active", True)
                .eq("sphere", vacancy["sphere"])
                .eq("schedule", vacancy["schedule"])
                .order("vip_until", desc=True, nullsfirst=False)
                .execute()
            )
        result = await self._run(query)
        return result.data

    async def list_all_active_seekers(self) -> list[dict[str, Any]]:
        def query():
            return (
                self.client.table("job_seekers")
                .select("*")
                .eq("active", True)
                .order("vip_until", desc=True, nullsfirst=False)
                .execute()
            )
        result = await self._run(query)
        return result.data

    async def record_notification(self, vacancy_id: int, seeker_id: int) -> None:
        def query():
            return (
                self.client.table("job_notifications")
                .upsert({"vacancy_id": vacancy_id, "seeker_id": seeker_id}, on_conflict="vacancy_id,seeker_id")
                .execute()
            )
        await self._run(query)

    async def set_reaction(self, vacancy_id: int, seeker_id: int, reaction: str) -> None:
        def query():
            return (
                self.client.table("job_notifications")
                .upsert(
                    {"vacancy_id": vacancy_id, "seeker_id": seeker_id, "reacted": reaction},
                    on_conflict="vacancy_id,seeker_id",
                )
                .execute()
            )
        await self._run(query)

    async def get_or_create_usage(self, user_id: int) -> dict[str, Any]:
        current_month = month_key()
        current_day = day_key()

        def select_query():
            return self.client.table("usage_limits").select("*").eq("user_id", user_id).maybe_single().execute()
        result = await self._run(select_query)
        if not result or not hasattr(result, 'data') or result.data is None:
            payload = {"user_id": user_id, "last_reset_month": current_month, "last_reset_day": current_day}
            def insert_query():
                return self.client.table("usage_limits").insert(payload).execute()
            inserted = await self._run(insert_query)
            return inserted.data[0]

        usage = result.data
        patch: dict[str, Any] = {}
        if usage.get("last_reset_month") != current_month:
            patch.update({"vacancies_this_month": 0, "urgent_broadcasts_this_month": 0, "last_reset_month": current_month})
        if usage.get("last_reset_day") != current_day:
            patch.update({"notifications_today": 0, "last_reset_day": current_day})
        if not patch:
            return usage

        def update_query():
            return self.client.table("usage_limits").update(patch).eq("user_id", user_id).execute()
        updated = await self._run(update_query)
        return updated.data[0]

    async def increment_vacancies_this_month(self, user_id: int) -> None:
        usage = await self.get_or_create_usage(user_id)
        value = int(usage.get("vacancies_this_month") or 0) + 1
        def query():
            return self.client.table("usage_limits").update({"vacancies_this_month": value}).eq("user_id", user_id).execute()
        await self._run(query)

    async def increment_notifications_today(self, user_id: int) -> None:
        usage = await self.get_or_create_usage(user_id)
        value = int(usage.get("notifications_today") or 0) + 1
        def query():
            return self.client.table("usage_limits").update({"notifications_today": value}).eq("user_id", user_id).execute()
        await self._run(query)

    async def increment_urgent_broadcasts_this_month(self, user_id: int) -> None:
        usage = await self.get_or_create_usage(user_id)
        value = int(usage.get("urgent_broadcasts_this_month") or 0) + 1
        def query():
            return self.client.table("usage_limits").update({"urgent_broadcasts_this_month": value}).eq("user_id", user_id).execute()
        await self._run(query)

    async def reset_monthly_usage(self) -> None:
        current_month = month_key()
        def query():
            return (
                self.client.table("usage_limits")
                .update({"vacancies_this_month": 0, "urgent_broadcasts_this_month": 0, "last_reset_month": current_month})
                .neq("user_id", 0)
                .execute()
            )
        await self._run(query)

    async def reset_daily_usage(self) -> None:
        current_day = day_key()
        def query():
            return (
                self.client.table("usage_limits")
                .update({"notifications_today": 0, "last_reset_day": current_day})
                .neq("user_id", 0)
                .execute()
            )
        await self._run(query)

    async def create_payment(
        self,
        *,
        user_id: int,
        payment_type: str,
        amount: int,
        feature: str,
        vacancy_id: int | None = None,
        status: str = PAYMENT_STATUS_PENDING,
        form_data: dict | None = None, # <-- НОВЫЙ ПАРАМЕТР
    ) -> dict[str, Any] | None:
        payload = {
            "user_id": user_id,
            "type": payment_type,
            "amount": amount,
            "feature": feature,
            "status": status,
            "vacancy_id": vacancy_id,
            "form_data": form_data, # <-- ДОБАВЛЯЕМ В PAYLOAD
        }
        def query():
            return self.client.table("payments").insert(payload).execute()
        result = await self._run(query)
        if not result or not result.data:
            return None
        return result.data[0]

    async def get_payment(self, payment_id: int) -> dict[str, Any] | None:
        def query():
            return self.client.table("payments").select("*").eq("id", payment_id).maybe_single().execute()
        result = await self._run(query)
        if not result or not result.data:
            return None
        return result.data

    async def reject_payment(self, payment_id: int) -> dict[str, Any] | None:
        def query():
            return self.client.table("payments").update({"status": "rejected"}).eq("id", payment_id).execute()
        result = await self._run(query)
        if not result or not result.data:
            return None
        return result.data[0]

    async def mark_payment_paid(
        self,
        payment_id: int,
        telegram_payment_charge_id: str | None = None,
        provider_payment_charge_id: str | None = None,
    ) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        payload = {
            "status": PAYMENT_STATUS_PAID,
            "paid_at": now.isoformat(),
            "expires_at": (now + timedelta(days=31)).isoformat(),
            "telegram_payment_charge_id": telegram_payment_charge_id,
            "provider_payment_charge_id": provider_payment_charge_id,
        }
        def query():
            return self.client.table("payments").update(payload).eq("id", payment_id).execute()
        result = await self._run(query)
        if not result or not result.data:
            return None
        return result.data[0]

    async def mark_latest_pending_payment_paid(self, user_id: int, feature: str, vacancy_id: int | None = None) -> dict[str, Any] | None:
        def select_query():
            request = (
                self.client.table("payments")
                .select("*")
                .eq("user_id", user_id)
                .eq("feature", feature)
                .eq("status", PAYMENT_STATUS_PENDING)
                .order("created_at", desc=True)
                .limit(1)
            )
            if vacancy_id is not None:
                request = request.eq("vacancy_id", vacancy_id)
            return request.execute()
        result = await self._run(select_query)
        if not result or not result.data:
            return None
        return await self.mark_payment_paid(result.data[0]["id"])

    async def has_active_paid_feature(self, user_id: int, feature: str) -> bool:
        now = datetime.now(UTC).isoformat()
        def query():
            return (
                self.client.table("payments")
                .select("id")
                .eq("user_id", user_id)
                .eq("feature", feature)
                .eq("status", PAYMENT_STATUS_PAID)
                .gt("expires_at", now)
                .limit(1)
                .execute()
            )
        result = await self._run(query)
        return bool(result.data)

    async def has_unlimited_vacancies(self, user_id: int) -> bool:
        return await self.has_active_paid_feature(user_id, FEATURE_UNLIMITED_VACANCIES)

    async def has_vip(self, user_id: int) -> bool:
        return await self.has_active_paid_feature(user_id, FEATURE_VIP_SEEKER)

    async def has_active_pin(self, user_id: int) -> bool:
        return await self.has_active_paid_feature(user_id, FEATURE_PIN_VACANCY)

    async def activate_vip(self, user_id: int, days: int = 31) -> dict[str, Any] | None:
        vip_until = (datetime.now(UTC) + timedelta(days=days)).isoformat()
        def query():
            return self.client.table("job_seekers").update({"vip_until": vip_until}).eq("user_id", user_id).execute()
        result = await self._run(query)
        if not result or not result.data:
            return None
        return result.data[0]

    async def schedule_unpin(self, vacancy_id: int, channel_message_id: int, unpin_at: datetime) -> None:
        payload = {"vacancy_id": vacancy_id, "channel_message_id": channel_message_id, "unpin_at": unpin_at.isoformat()}
        def query():
            return self.client.table("scheduled_unpins").insert(payload).execute()
        await self._run(query)

    async def list_due_unpins(self) -> list[dict[str, Any]]:
        now = datetime.now(UTC).isoformat()
        def query():
            return self.client.table("scheduled_unpins").select("*").eq("status", "scheduled").lte("unpin_at", now).execute()
        result = await self._run(query)
        return result.data

    async def mark_unpin_done(self, unpin_id: int, failed: bool = False) -> None:
        status = "failed" if failed else "done"
        def query():
            return self.client.table("scheduled_unpins").update({"status": status}).eq("id", unpin_id).execute()
        await self._run(query)

    async def register_referral(self, referrer_id: int, referred_id: int) -> bool:
        if referrer_id == referred_id:
            return False
        def select_query():
            return self.client.table("referrals").select("referred_id").eq("referred_id", referred_id).maybe_single().execute()
        existing = await self._run(select_query)
        if existing and existing.data:
            return False
        payload = {"referrer_id": referrer_id, "referred_id": referred_id}
        def insert_query():
            return self.client.table("referrals").insert(payload).execute()
        result = await self._run(insert_query)
        return bool(result.data)

    async def count_referrals(self, user_id: int) -> int:
        def query():
            return self.client.table("referrals").select("referred_id", count="exact").eq("referrer_id", user_id).execute()
        result = await self._run(query)
        return int(result.count or 0)

    async def get_referrer_for_user(self, user_id: int) -> int | None:
        def query():
            return self.client.table("referrals").select("referrer_id").eq("referred_id", user_id).maybe_single().execute()
        result = await self._run(query)
        if not result or not result.data:
            return None
        return int(result.data["referrer_id"])

    async def referral_vip_bonus_available(self, user_id: int, referrals_count: int) -> bool:
        if referrals_count < 10:
            return False
        def query():
            return (
                self.client.table("referrals")
                .select("referred_id")
                .eq("referrer_id", user_id)
                .eq("bonus_vip_granted", True)
                .limit(1)
                .execute()
            )
        result = await self._run(query)
        return not bool(result.data)

    async def mark_referral_vip_bonus_used(self, user_id: int) -> None:
        def query():
            return self.client.table("referrals").update({"bonus_vip_granted": True}).eq("referrer_id", user_id).execute()
        await self._run(query)

    async def admin_stats(self) -> dict[str, int]:
        def seekers():
            return self.client.table("job_seekers").select("user_id", count="exact").execute()
        def active_vacancies():
            return self.client.table("job_vacancies").select("id", count="exact").eq("status", VACANCY_STATUS_APPROVED).execute()
        def closed_vacancies():
            return self.client.table("job_vacancies").select("id", count="exact").eq("status", VACANCY_STATUS_CLOSED).execute()
        def found_work():
            return self.client.table("job_seekers").select("user_id", count="exact").eq("found_work", True).execute()
        def paid_users():
            return self.client.table("payments").select("user_id", count="exact").eq("status", PAYMENT_STATUS_PAID).execute()
        def paid_rows():
            return self.client.table("payments").select("amount").eq("status", PAYMENT_STATUS_PAID).eq("type", "stars").execute()
        seeker_result, active_result, closed_result, found_result, paid_users_result, paid_rows_result = await asyncio.gather(
            self._run(seekers),
            self._run(active_vacancies),
            self._run(closed_vacancies),
            self._run(found_work),
            self._run(paid_users),
            self._run(paid_rows),
        )
        return {
            "seekers_total": int(seeker_result.count or 0),
            "active_vacancies": int(active_result.count or 0),
            "closed_vacancies": int(closed_result.count or 0),
            "found_work": int(found_result.count or 0),
            "paid_users": int(paid_users_result.count or 0),
            "stars_earned": sum(int(row.get("amount") or 0) for row in paid_rows_result.data),
        }

    async def employer_stats(self, employer_id: int) -> dict[str, int]:
        def vacancies():
            return self.client.table("job_vacancies").select("id,sphere,status").eq("employer_id", employer_id).execute()
        vacancy_result = await self._run(vacancies)
        vacancy_ids = [row["id"] for row in vacancy_result.data]
        main_sphere = vacancy_result.data[0]["sphere"] if vacancy_result.data else None
        def notifications():
            return self.client.table("job_notifications").select("id", count="exact").in_("vacancy_id", vacancy_ids or [-1]).execute()
        def likes():
            return (
                self.client.table("job_notifications")
                .select("id", count="exact")
                .in_("vacancy_id", vacancy_ids or [-1])
                .eq("reacted", "like")
                .execute()
            )
        def seekers_in_sphere():
            request = self.client.table("job_seekers").select("user_id", count="exact").eq("active", True)
            if main_sphere:
                request = request.eq("sphere", main_sphere)
            return request.execute()
        notifications_result, likes_result, seekers_result = await asyncio.gather(
            self._run(notifications), self._run(likes), self._run(seekers_in_sphere)
        )
        active_vacancies = sum(1 for row in vacancy_result.data if row.get("status") == "approved")
        pending_vacancies = sum(1 for row in vacancy_result.data if row.get("status") == "pending")
        closed_vacancies = sum(1 for row in vacancy_result.data if row.get("status") == "closed")
        rejected_vacancies = sum(1 for row in vacancy_result.data if row.get("status") == "rejected")
        return {
            "vacancies_total": int(vacancy_result.count or 0),
            "active_vacancies": active_vacancies,
            "pending_vacancies": pending_vacancies,
            "closed_vacancies": closed_vacancies,
            "rejected_vacancies": rejected_vacancies,
            "views": int(notifications_result.count or 0),
            "responses": int(likes_result.count or 0),
            "seekers_in_sphere": int(seekers_result.count or 0),
        }

    async def seeker_stats(self, user_id: int) -> dict[str, Any]:
        seeker = await self.get_seeker(user_id)
        def notifications():
            return self.client.table("job_notifications").select("id", count="exact").eq("seeker_id", user_id).execute()
        def likes():
            return (
                self.client.table("job_notifications")
                .select("id", count="exact")
                .eq("seeker_id", user_id)
                .eq("reacted", "like")
                .execute()
            )
        notifications_result, likes_result = await asyncio.gather(self._run(notifications), self._run(likes))
        return {
            "created_at": seeker.get("created_at") if seeker else None,
            "views": int(notifications_result.count or 0),
            "responses": int(likes_result.count or 0),
            "referrals": await self.count_referrals(user_id),
            "vip_until": seeker.get("vip_until") if seeker else None,
        }

    async def weekly_stats(self) -> dict[str, Any]:
        since = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        def seekers():
            return self.client.table("job_seekers").select("user_id", count="exact").gte("created_at", since).execute()
        def vacancies():
            return self.client.table("job_vacancies").select("id,employer_id,employer_username,sphere").gte("created_at", since).execute()
        def found():
            return self.client.table("job_seekers").select("user_id", count="exact").eq("found_work", True).gte("updated_at", since).execute()
        seeker_result, vacancy_result, found_result = await asyncio.gather(
            self._run(seekers), self._run(vacancies), self._run(found)
        )
        sphere_counts: dict[str, int] = {}
        vacancy_by_id: dict[int, dict[str, Any]] = {}
        employer_vacancy_counts: dict[int, int] = {}
        employer_usernames: dict[int, str] = {}
        for row in vacancy_result.data:
            sphere_counts[row["sphere"]] = sphere_counts.get(row["sphere"], 0) + 1
            vacancy_by_id[row["id"]] = row
            employer_id = row["employer_id"]
            employer_vacancy_counts[employer_id] = employer_vacancy_counts.get(employer_id, 0) + 1
            employer_usernames[employer_id] = row.get("employer_username") or f"id{employer_id}"
        def likes():
            request = (
                self.client.table("job_notifications")
                .select("vacancy_id")
                .eq("reacted", "like")
                .gte("sent_at", since)
            )
            if vacancy_by_id:
                request = request.in_("vacancy_id", list(vacancy_by_id))
            return request.execute()
        likes_result = await self._run(likes)
        employer_like_counts: dict[int, int] = {}
        for row in likes_result.data:
            vacancy = vacancy_by_id.get(row["vacancy_id"])
            if not vacancy:
                continue
            employer_id = vacancy["employer_id"]
            employer_like_counts[employer_id] = employer_like_counts.get(employer_id, 0) + 1
        top_employers = []
        for employer_id, likes_count in sorted(employer_like_counts.items(), key=lambda item: item[1], reverse=True)[:3]:
            username = employer_usernames.get(employer_id, f"id{employer_id}")
            label = f"@{username}" if not str(username).startswith("id") and not str(username).startswith("@") else str(username)
            top_employers.append(
                f"{label} — {employer_vacancy_counts.get(employer_id, 0)} вакансий, {likes_count} откликов"
            )
        popular_sphere = max(sphere_counts, key=sphere_counts.get) if sphere_counts else "пока нет данных"
        return {
            "new_seekers": int(seeker_result.count or 0),
            "new_vacancies": len(vacancy_result.data),
            "found_work": int(found_result.count or 0),
            "popular_sphere": popular_sphere,
            "top_employers": top_employers,
        }

    async def count_employer_vacancies(self, employer_id: int) -> int:
        def query():
            return self.client.table("job_vacancies").select("id", count="exact").eq("employer_id", employer_id).execute()
        result = await self._run(query)
        return int(result.count or 0)

    async def get_setting(self, key: str) -> str | None:
        def query():
            return self.client.table("bot_settings").select("value").eq("key", key).maybe_single().execute()
        result = await self._run(query)
        if not result or not result.data:
            return None
        return result.data["value"]

    async def set_setting(self, key: str, value: str) -> None:
        def query():
            return self.client.table("bot_settings").upsert({"key": key, "value": value}, on_conflict="key").execute()
        await self._run(query)

    async def get_price(self, service: str) -> int | None:
        value = await self.get_setting(f"price_{service}")
        if value and value.isdigit():
            return int(value)
        return None

    async def get_user_active_role(self, user_id: int) -> dict | None:
        def query():
            return self.client.table("user_active_role").select("*").eq("user_id", user_id).maybe_single().execute()
        result = await self._run(query)
        return result.data if result and result.data else None

    async def set_user_active_role(self, user_id: int, role: str) -> None:
        payload = {"user_id": user_id, "role": role}
        def query():
            return self.client.table("user_active_role").upsert(payload, on_conflict="user_id").execute()
        await self._run(query)

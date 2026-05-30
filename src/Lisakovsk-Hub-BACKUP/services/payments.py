from __future__ import annotations

from dataclasses import dataclass

from constants import FEATURE_PRICES_STARS, FEATURE_TITLES


@dataclass(frozen=True)
class FeatureRequest:
    feature: str
    amount: int
    title: str
    vacancy_id: int | None = None


def build_payment_payload(feature: str, vacancy_id: int | None = None) -> str:
    suffix = "" if vacancy_id is None else f":{vacancy_id}"
    return f"joblis:{feature}{suffix}"


def parse_payment_payload(payload: str) -> tuple[str, int | None]:
    prefix = "joblis:"
    if not payload.startswith(prefix):
        raise ValueError("unknown payment payload")
    parts = payload.removeprefix(prefix).split(":", 1)
    feature = parts[0]
    vacancy_id = int(parts[1]) if len(parts) == 2 and parts[1] else None
    if feature not in FEATURE_PRICES_STARS:
        raise ValueError("unknown feature")
    return feature, vacancy_id


def get_feature_request(feature: str, vacancy_id: int | None = None) -> FeatureRequest:
    return FeatureRequest(
        feature=feature,
        amount=FEATURE_PRICES_STARS[feature],
        title=FEATURE_TITLES[feature],
        vacancy_id=vacancy_id,
    )

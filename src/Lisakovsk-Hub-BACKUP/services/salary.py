from __future__ import annotations

import re

from constants import NOT_IMPORTANT


def parse_salary_range(text: str) -> tuple[int | None, int | None]:
    normalized = text.strip().lower().replace("—", "-").replace("–", "-")
    if normalized == NOT_IMPORTANT.lower():
        return None, None

    parts = [int(match.replace(" ", "")) for match in re.findall(r"\d[\d ]*", normalized)]
    if not parts:
        raise ValueError("salary range is empty")
    if len(parts) == 1:
        return parts[0], None
    return min(parts[0], parts[1]), max(parts[0], parts[1])

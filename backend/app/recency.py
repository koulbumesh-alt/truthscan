from __future__ import annotations

from datetime import UTC, datetime, timedelta

LATEST_RUMOUR_DAYS = 14


def parse_timestamp(value: str | datetime | None) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def is_recent_rumour(
    value: str | datetime | None,
    *,
    now: datetime | None = None,
    days: int = LATEST_RUMOUR_DAYS,
) -> bool:
    """Accept published reviews from the current rolling window only.

    Unknown publication dates are excluded: a newly fetched URL is not proof
    that its underlying rumour or review is new.
    """
    parsed = parse_timestamp(value)
    reference = (now or datetime.now(UTC)).astimezone(UTC)
    if parsed is None:
        return False
    return reference - timedelta(days=days) <= parsed <= reference + timedelta(days=1)

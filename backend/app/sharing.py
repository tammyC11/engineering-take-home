"""Which diary entries a share covers, in the patient's own days (see NOTES.md, time zones)."""

from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models import DiaryEntry, Share

# Written by app v1: local wall-clock time, stored as if it were UTC.
APP_V1 = "app-v1"


def local_day(entry: DiaryEntry, timezone: str) -> date:
    """The day the entry belongs to in the patient's diary."""
    if entry.source == APP_V1:
        return entry.recorded_at.astimezone(UTC).date()
    return entry.recorded_at.astimezone(ZoneInfo(timezone)).date()


def actual_recorded_at(entry: DiaryEntry, timezone: str) -> datetime:
    """When the entry was really recorded, in UTC; repairs app-v1 timestamps."""
    if entry.source == APP_V1:
        wall_clock = entry.recorded_at.astimezone(UTC).replace(tzinfo=ZoneInfo(timezone))
        return wall_clock.astimezone(UTC)
    return entry.recorded_at


def covering_shares(entry: DiaryEntry, shares: Sequence[Share]) -> list[Share]:
    return [s for s in shares if s.from_date <= local_day(entry, s.timezone) <= s.to_date]


def search_window(shares: Sequence[Share]) -> tuple[datetime, datetime]:
    """A UTC range that surely contains every covered entry, for the database query. It is a
    day wider on each side than any UTC offset; covering_shares() then decides exactly."""
    start = min(s.from_date for s in shares) - timedelta(days=1)
    end = max(s.to_date for s in shares) + timedelta(days=2)
    return datetime.combine(start, time.min, UTC), datetime.combine(end, time.min, UTC)

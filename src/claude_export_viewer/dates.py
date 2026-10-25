"""Dates: reading the ISO dates of the export, and showing them in French.

Dates shown to the reader are in the local time of this computer
("23/10/2026 à 10:00"); dates stored in the archive are ISO strings in UTC.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def parse(value: Any) -> datetime | None:
    """A datetime from an ISO string (a trailing "Z" is accepted) or a datetime; None if unreadable."""
    if isinstance(value, datetime):
        return value
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def utc(d: datetime) -> datetime:
    """The same moment in UTC (a date without time zone is taken as UTC)."""
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def iso_utc(d: datetime) -> str:
    """How dates are stored in the archive: "2026-10-20T08:00:00+00:00"."""
    return utc(d).replace(microsecond=0).isoformat()


def local(d: datetime) -> datetime:
    """Local time of this computer (a date without time zone is left as it is)."""
    return d.astimezone() if d.tzinfo is not None else d


def date_fr(value: Any, to_local: bool = True) -> str:
    """"23/10/2026" ("" if there is no readable date)."""
    d = parse(value)
    if d is None:
        return ""
    return (local(d) if to_local else d).strftime("%d/%m/%Y")


def datetime_fr(value: Any) -> str:
    """"23/10/2026 à 10:00", local time ("" if there is no readable date)."""
    d = parse(value)
    return local(d).strftime("%d/%m/%Y à %H:%M") if d is not None else ""

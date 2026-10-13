"""Narrow time checks for short-lived notices and their rendered dates."""

import re
from datetime import datetime, timedelta, timezone


MYT = timezone(timedelta(hours=8))
WEATHER_NOTICE = re.compile(
    r"thunderstorm|heavy rain|gusty winds|weather (?:warning|advisory)|"
    r"amaran ribut petir|hujan lebat",
    re.IGNORECASE,
)
UNTIL_HOUR = re.compile(r"\buntil\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.IGNORECASE)
FUTURE_DAY = re.compile(r"\btomorrow\b|\besok\b|\bnext day\b", re.IGNORECASE)
MONTH_DAY = re.compile(
    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2})\b",
    re.IGNORECASE,
)
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
RELATIVE_JA = re.compile(r"本日|今日|明日|今朝|今夜|今夕|昨夜|昨日")


def notice_deadline(title: str, description: str, published_at: datetime) -> datetime | None:
    """Resolve only same-day weather deadlines that the RSS text makes clear."""
    text = f"{title} {description}"
    if not WEATHER_NOTICE.search(text) or FUTURE_DAY.search(text):
        return None
    matches = list(UNTIL_HOUR.finditer(text))
    if len(matches) != 1 or published_at.tzinfo is None:
        return None
    match = matches[0]
    hour, minute = int(match[1]), int(match[2] or 0)
    if not 1 <= hour <= 12 or minute > 59:
        return None
    hour = hour % 12 + (12 if match[3].lower() == "pm" else 0)
    published_myt = published_at.astimezone(MYT)
    month_names = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
    if any(
        month_names.index(date_match[1][:3].lower()) + 1 != published_myt.month
        or int(date_match[2]) != published_myt.day
        for date_match in MONTH_DAY.finditer(text)
    ):
        return None
    if any(date_match.group() != published_myt.date().isoformat() for date_match in ISO_DATE.finditer(text)):
        return None
    deadline = published_myt.replace(hour=hour, minute=minute, second=0, microsecond=0)
    # An already-past hour in the source cannot safely be resolved to that day.
    if deadline < published_myt:
        return None
    return deadline


def stale_relative_date(published_at: str, publication_as_of: str, rendered_text: str, source_text: str) -> bool:
    """Reject relative Japanese dates only for a previous-day, time-bound source."""
    if not (UNTIL_HOUR.search(source_text) or WEATHER_NOTICE.search(source_text)) or not RELATIVE_JA.search(rendered_text):
        return False
    try:
        source_time = datetime.fromisoformat(published_at)
        publication_time = datetime.fromisoformat(publication_as_of)
    except (TypeError, ValueError):
        return False
    if source_time.tzinfo is None or publication_time.tzinfo is None:
        return False
    return source_time.astimezone(MYT).date() != publication_time.astimezone(MYT).date()

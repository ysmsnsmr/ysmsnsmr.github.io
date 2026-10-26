"""Narrow time checks for short-lived notices and their rendered dates."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone


MYT = timezone(timedelta(hours=8))
WEATHER_NOTICE = re.compile(
    r"thunderstorm|severe storms?|heavy rain|gusty winds|weather (?:warning|advisory|forecast)|"
    r"amaran ribut petir|ribut petir|hujan lebat|ramalan cuaca",
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
SOURCE_DAY_JA = re.compile(r"本日|今日|今朝")
SOURCE_TODAY = re.compile(
    r"\btoday\b|\bhari ini\b|\b(?:as at|as of)\s+\d{1,2}(?:[.:]\d{1,2})?\s*(?:am|pm)\b",
    re.IGNORECASE,
)
SOURCE_THIS_MORNING = re.compile(r"\bthis morning\b|\bpagi (?:ini|tadi)\b", re.IGNORECASE)
TODAY = re.compile(r"\btoday\b|\bhari ini\b", re.IGNORECASE)
WEATHER_FORECAST = re.compile(r"\b(?:warning|warns?|forecast|expected|advisory|alert|amaran|dijangka|ramalan)\b", re.IGNORECASE)
HAZE = re.compile(r"\bhaze\b|\bjerebu\b", re.IGNORECASE)
AIR_QUALITY_READING = re.compile(r"\b(?:API|IPU|APIMS|air pollutant index|air quality index|indeks pencemar udara)\b", re.IGNORECASE)
SNAPSHOT_CUE = re.compile(r"\b(?:as of|as at|readings?|records?|recorded|highest|top|bacaan|mencatat|paras)\b", re.IGNORECASE)
SNAPSHOT_AS_OF = re.compile(r"\b(?:as of|as at)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.IGNORECASE)
HAZE_ACTION = re.compile(r"\b(?:schools?|classes|examinations?|closures?|closed|reopen(?:ing)?|"
                         r"flights?|trains?|buses|roads?|transport|service disruption|services? suspended)\b", re.IGNORECASE)
KLANG_VALLEY = re.compile(
    r"\b(?:Klang Valley|Greater Kuala Lumpur|Kuala Lumpur|Putrajaya|Petaling(?: Jaya| Perdana)?|"
    r"Hulu Langat|Sepang|Shah Alam|Subang(?: Jaya)?|Klang|Puchong|Cheras|Ampang|Gombak)\b",
    re.IGNORECASE,
)
DATELINE = re.compile(r"^\s*[A-Z][A-Z ]{2,},\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2}\s*[—–-]\s*", re.IGNORECASE)


def _article_text(title: str, description: str) -> str:
    return f"{title} {DATELINE.sub('', description)}"


def _target_date(title: str, description: str, published_at: datetime) -> date | None:
    if published_at.tzinfo is None:
        return None
    published_day = published_at.astimezone(MYT).date()
    month_names = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
    for text in (title, DATELINE.sub("", description)):
        future = bool(FUTURE_DAY.search(text))
        today = bool(TODAY.search(text))
        if future and today:
            return None
        if future:
            return published_day + timedelta(days=1)
        if today:
            return published_day
        iso_dates = list(ISO_DATE.finditer(text))
        if len(iso_dates) == 1:
            try:
                candidate = date.fromisoformat(iso_dates[0].group())
            except ValueError:
                return None
            return candidate if (candidate - published_day).days in (-1, 0, 1) else None
        if len(iso_dates) > 1:
            return None
        dates = list(MONTH_DAY.finditer(text))
        if len(dates) == 1:
            month = month_names.index(dates[0][1][:3].lower()) + 1
            day = int(dates[0][2])
            try:
                candidate = date(published_day.year, month, day)
            except ValueError:
                return None
            if (candidate - published_day).days in (-1, 0, 1):
                return candidate
            return None
        if len(dates) > 1:
            return None
    return None


def haze_action_target_date(title: str, description: str, published_at: datetime) -> date | None:
    text = _article_text(title, description)
    if not HAZE.search(text) or not HAZE_ACTION.search(text):
        return None
    return _target_date(title, description, published_at)


def klang_valley_area_in_body(body: str) -> bool:
    return bool(KLANG_VALLEY.search(DATELINE.sub("", body)))


def _snapshot_time(title: str, published_at: datetime) -> datetime:
    match = SNAPSHOT_AS_OF.search(title)
    if match:
        hour, minute = int(match[1]), int(match[2] or "0")
        if 1 <= hour <= 12 and minute <= 59:
            hour = hour % 12 + (12 if match[3].lower() == "pm" else 0)
            return datetime.combine(published_at.astimezone(MYT).date(), time(hour, minute), tzinfo=MYT)
    return published_at.astimezone(MYT)


def publication_rejection_reason(
    title: str, description: str, published_at: datetime, publication_as_of: datetime
) -> str | None:
    """Require dated source evidence before carrying time-sensitive news into a daily edition."""
    text = _article_text(title, description)
    short_weather = WEATHER_NOTICE.search(text) and (WEATHER_FORECAST.search(title) or UNTIL_HOUR.search(text))
    haze_action = HAZE.search(text) and HAZE_ACTION.search(text)
    air_quality_snapshot = AIR_QUALITY_READING.search(title) and SNAPSHOT_CUE.search(title)
    if not short_weather and not haze_action and not air_quality_snapshot:
        return None
    if published_at.tzinfo is None or publication_as_of.tzinfo is None:
        return "unverified_publication_time"
    source_day = published_at.astimezone(MYT).date()
    publication_day = publication_as_of.astimezone(MYT).date()
    previous_noon = datetime.combine(publication_day - timedelta(days=1), time(12), tzinfo=MYT)
    if air_quality_snapshot and not haze_action and _snapshot_time(title, published_at) <= previous_noon:
        if _target_date(title, description, published_at) != publication_day:
            return "stale_previous_noon_observation"
    if short_weather:
        deadline = notice_deadline(title, description, published_at)
        if deadline is not None and deadline <= publication_as_of.astimezone(MYT):
            return "expired_time_bound_notice"
        target_day = _target_date(title, description, published_at)
        if target_day is None and (FUTURE_DAY.search(text) or TODAY.search(text) or MONTH_DAY.search(text) or ISO_DATE.search(text)):
            return "unverified_weather_target_day"
        target_day = target_day or source_day
        if target_day != publication_day:
            return "weather_not_for_publication_day"
        if deadline is None:
            return "unverified_weather_validity"
    if source_day < publication_day and haze_action:
        target_day = haze_action_target_date(title, description, published_at)
        if target_day != publication_day:
            return "haze_action_not_for_publication_day"
        if not KLANG_VALLEY.search(text):
            return "haze_action_area_unverified"
    return None


def notice_deadline(title: str, description: str, published_at: datetime) -> datetime | None:
    """Resolve a weather deadline only when the article's target day is clear."""
    text = f"{title} {description}"
    if not WEATHER_NOTICE.search(text):
        return None
    matches = {(match[1], match[2] or "0", match[3].lower()) for match in UNTIL_HOUR.finditer(text)}
    if len(matches) != 1 or published_at.tzinfo is None:
        return None
    raw_hour, raw_minute, period = matches.pop()
    hour, minute = int(raw_hour), int(raw_minute)
    if not 1 <= hour <= 12 or minute > 59:
        return None
    hour = hour % 12 + (12 if period == "pm" else 0)
    published_myt = published_at.astimezone(MYT)
    target_day = _target_date(title, description, published_at)
    clean_text = _article_text(title, description)
    if target_day is None and (FUTURE_DAY.search(clean_text) or TODAY.search(clean_text) or MONTH_DAY.search(clean_text) or ISO_DATE.search(clean_text)):
        return None
    target_day = target_day or published_myt.date()
    deadline = datetime(target_day.year, target_day.month, target_day.day, hour, minute, tzinfo=MYT)
    # An already-past hour in the source cannot safely be resolved to that day.
    if deadline < published_myt:
        return None
    return deadline


def stale_relative_date(published_at: str, publication_as_of: str, rendered_text: str, source_text: str) -> bool:
    """Reject relative Japanese dates only for a previous-day, time-bound source."""
    time_sensitive = (
        UNTIL_HOUR.search(source_text)
        or (WEATHER_NOTICE.search(source_text) and WEATHER_FORECAST.search(source_text))
        or (HAZE.search(source_text) and HAZE_ACTION.search(source_text))
    )
    if not time_sensitive or not RELATIVE_JA.search(rendered_text):
        return False
    try:
        source_time = datetime.fromisoformat(published_at)
        publication_time = datetime.fromisoformat(publication_as_of)
    except (TypeError, ValueError):
        return False
    if source_time.tzinfo is None or publication_time.tzinfo is None:
        return False
    return source_time.astimezone(MYT).date() != publication_time.astimezone(MYT).date()


def previous_day_source_date(published_at: str, publication_as_of: str) -> date | None:
    try:
        source_time = datetime.fromisoformat(published_at)
        publication_time = datetime.fromisoformat(publication_as_of)
    except (TypeError, ValueError):
        return None
    if source_time.tzinfo is None or publication_time.tzinfo is None:
        return None
    source_day = source_time.astimezone(MYT).date()
    return source_day if source_day < publication_time.astimezone(MYT).date() else None


def stale_source_day_reference(published_at: str, publication_as_of: str, rendered_text: str) -> bool:
    return previous_day_source_date(published_at, publication_as_of) is not None and bool(
        SOURCE_DAY_JA.search(rendered_text)
    )


def anchor_source_day_reference(
    published_at: str, publication_as_of: str, rendered_text: str, source_text: str
) -> str:
    """Use the source day only where the source itself supports a relative-day reading."""
    source_day = previous_day_source_date(published_at, publication_as_of)
    if source_day is None or stale_relative_date(published_at, publication_as_of, rendered_text, source_text):
        return rendered_text
    absolute = f"{source_day.year}年{source_day.month}月{source_day.day}日"
    text = rendered_text
    for marker in ("本日", "今日"):
        text = re.sub(rf"{marker}\s*(?={re.escape(absolute)})", "", text)
        text = re.sub(rf"{marker}\s*[（(]\s*{re.escape(absolute)}\s*[）)]", absolute, text)
    if SOURCE_TODAY.search(source_text):
        text = re.sub(r"本日|今日", absolute, text)
    if SOURCE_THIS_MORNING.search(source_text):
        text = text.replace("今朝", f"{absolute}朝")
    return text


def missing_haze_target_date(
    published_at: str, publication_as_of: str, title: str, description: str, rendered_text: str
) -> bool:
    try:
        source_time = datetime.fromisoformat(published_at)
        publication_time = datetime.fromisoformat(publication_as_of)
    except (TypeError, ValueError):
        return False
    if source_time.tzinfo is None or publication_time.tzinfo is None:
        return False
    target_day = haze_action_target_date(title, description, source_time)
    if target_day is None or source_time.astimezone(MYT).date() >= publication_time.astimezone(MYT).date():
        return False
    return not (
        re.search(rf"{target_day.month}月\s*{target_day.day}日", rendered_text)
        or target_day.isoformat() in rendered_text
    )

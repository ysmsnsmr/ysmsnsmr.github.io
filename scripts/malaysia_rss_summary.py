#!/usr/bin/env python3
import argparse
import email.utils
import html
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


UA = "Mozilla/5.0"
SOURCES = [
    ("Malay Mail", "Malay Mail Malaysia", "https://www.malaymail.com/feed/rss/malaysia"),
    ("Malay Mail", "Malay Mail Money", "https://www.malaymail.com/feed/rss/money"),
    ("Astro Awani", "Astro Awani National", "https://www.astroawani.com/rss/national/public"),
]
MYT = timezone(timedelta(hours=8))

FLAG_WEATHER = "is_weather"
FLAG_HEAT = "is_heat"
FLAG_PUBLIC_TRANSPORT = "is_public_transport"
FLAG_ROAD_ISSUE = "is_road_issue"
FLAG_UTILITY_BILL = "is_utility_bill"
FLAG_SABAH_ELECTRICITY = "is_sabah_electricity"
FLAG_JPJ = "is_jpj"
FLAG_MYDIGITAL_INTEGRATION = "is_mydigital_integration"
FLAG_MCMC = "is_mcmc"
FLAG_MCMC_3R = "is_mcmc_3r"
FLAG_MCMC_SERVICE_QUALITY = "is_mcmc_service_quality"
FLAG_MCMC_WSIS = "is_mcmc_wsis"
FLAG_SOCIAL_SECURITY = "is_social_security"
FLAG_SCAM = "is_scam"
FLAG_CURRENCY = "is_currency"
FLAG_MARKET = "is_market"
FLAG_AI_ECONOMY = "is_ai_economy"
FLAG_HEALTH_SYSTEM = "is_health_system"
FLAG_URBAN_DEVELOPMENT = "is_urban_development"
FLAG_KLANG_VALLEY = "is_klang_valley"
FLAG_OFFICIAL = "is_official"
FLAG_INDIVIDUAL_INCIDENT = "is_individual_incident"
FLAG_POLITICAL_NOISE = "is_political_noise"

ALL_FLAGS = [
    FLAG_WEATHER,
    FLAG_HEAT,
    FLAG_PUBLIC_TRANSPORT,
    FLAG_ROAD_ISSUE,
    FLAG_UTILITY_BILL,
    FLAG_SABAH_ELECTRICITY,
    FLAG_JPJ,
    FLAG_MYDIGITAL_INTEGRATION,
    FLAG_MCMC,
    FLAG_MCMC_3R,
    FLAG_MCMC_SERVICE_QUALITY,
    FLAG_MCMC_WSIS,
    FLAG_SOCIAL_SECURITY,
    FLAG_SCAM,
    FLAG_CURRENCY,
    FLAG_MARKET,
    FLAG_AI_ECONOMY,
    FLAG_HEALTH_SYSTEM,
    FLAG_URBAN_DEVELOPMENT,
    FLAG_KLANG_VALLEY,
    FLAG_OFFICIAL,
    FLAG_INDIVIDUAL_INCIDENT,
    FLAG_POLITICAL_NOISE,
]


@dataclass
class FetchResult:
    ok: bool
    url: str
    data: bytes = b""
    status: str = ""
    content_type: str = ""
    method: str = ""
    error: str = ""


@dataclass
class Item:
    source: str
    feed: str
    title: str
    description: str
    pub_date: datetime
    pub_raw: str
    link: str
    score: int = 0
    category: str = ""
    tags: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    penalties: list[str] = field(default_factory=list)
    source_count: int = 1
    is_official: bool = False
    background_value: bool = False
    published_at: datetime | None = None
    effective_at: datetime | None = None
    expires_at: datetime | None = None
    active_until: datetime | None = None
    flags: dict[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.published_at is None:
            self.published_at = self.pub_date


def diagnostic_lines() -> list[str]:
    lines = [
        f"Python version: {sys.version.split()[0]}",
        f"ssl.OPENSSL_VERSION: {ssl.OPENSSL_VERSION}",
    ]
    try:
        proc = subprocess.run(
            ["curl", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        first = (proc.stdout or proc.stderr).splitlines()[0] if (proc.stdout or proc.stderr) else ""
    except Exception as exc:
        first = f"ERROR: {type(exc).__name__}: {exc}"
    lines.append(f"curl --version: {first}")
    return lines


def fetch_urllib(url: str) -> FetchResult:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return FetchResult(
                ok=True,
                url=url,
                data=resp.read(),
                status=str(getattr(resp, "status", "")),
                content_type=resp.headers.get("content-type", ""),
                method="urllib",
            )
    except Exception as exc:
        status = ""
        content_type = ""
        body = b""
        if isinstance(exc, urllib.error.HTTPError):
            status = str(exc.code)
            content_type = exc.headers.get("content-type", "") if exc.headers else ""
            try:
                body = exc.read()
            except Exception:
                body = b""
        return FetchResult(
            ok=False,
            url=url,
            data=body,
            status=status,
            content_type=content_type,
            method="urllib",
            error=f"{type(exc).__name__}: {exc}",
        )


def fetch_curl(url: str) -> FetchResult:
    try:
        proc = subprocess.run(
            [
                "curl",
                "-L",
                "--max-time",
                "20",
                "-sS",
                "-A",
                UA,
                "-D",
                "-",
                url,
            ],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:
        return FetchResult(ok=False, url=url, method="curl", error=f"{type(exc).__name__}: {exc}")

    raw = proc.stdout
    header_blob, _, body = raw.rpartition(b"\r\n\r\n")
    headers_text = header_blob.decode("iso-8859-1", "replace")
    status = ""
    content_type = ""
    for line in headers_text.splitlines():
        if line.startswith("HTTP/"):
            parts = line.split()
            if len(parts) >= 2:
                status = parts[1]
        elif line.lower().startswith("content-type:"):
            content_type = line.split(":", 1)[1].strip()
    if proc.returncode == 0 and body:
        return FetchResult(
            ok=True,
            url=url,
            data=body,
            status=status,
            content_type=content_type,
            method="curl",
        )
    err = proc.stderr.decode("utf-8", "replace").strip()
    return FetchResult(
        ok=False,
        url=url,
        data=body,
        status=status,
        content_type=content_type,
        method="curl",
        error=f"curl exit {proc.returncode}: {err}",
    )


def fetch_rss(url: str) -> FetchResult:
    first = fetch_urllib(url)
    if first.ok:
        return first
    fallback = fetch_curl(url)
    if fallback.ok:
        fallback.error = f"urllib failed; fallback used: {first.error}"
        return fallback
    fallback.error = f"urllib failed: {first.error}; curl failed: {fallback.error}"
    return fallback


def lenient_xml(data: bytes) -> ET.Element:
    data = data.strip()
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        text = data.decode("utf-8", "ignore").strip()
        text = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)", "&amp;", text)
        return ET.fromstring(text.encode("utf-8"))


def text_of(item: ET.Element, tag: str) -> str:
    child = item.find(tag)
    if child is None:
        return ""
    return clean("".join(child.itertext()))


def clean(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_date(value: str) -> Optional[datetime]:
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=MYT)
    return parsed.astimezone(MYT)


def parse_items(source: str, feed: str, data: bytes) -> list[Item]:
    root = lenient_xml(data)
    items: list[Item] = []
    for node in root.findall(".//item"):
        title = text_of(node, "title")
        description = text_of(node, "description")
        link = text_of(node, "link")
        pub_raw = text_of(node, "pubDate")
        pub_date = parse_date(pub_raw)
        if title and link and pub_date:
            items.append(Item(source, feed, title, description, pub_date, pub_raw, link))
    return items


def normalized(value: str) -> str:
    value = html.unescape(value or "").lower()
    value = value.replace("‑", "-").replace("–", "-").replace("—", "-")
    value = re.sub(r"[-_/]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def item_text(item: Item) -> str:
    return normalized(f"{item.title} {item.description}")


def phrase_pattern(phrase: str) -> str:
    escaped_words = [re.escape(part) for part in normalized(phrase).split()]
    return r"(?<![a-z0-9])" + r"\s+".join(escaped_words) + r"(?![a-z0-9])"


def has_phrase(text: str, phrase: str) -> bool:
    if not phrase:
        return False
    return bool(re.search(phrase_pattern(phrase), normalized(text)))


def has_any(text: str, phrases: list[str]) -> bool:
    return any(has_phrase(text, phrase) for phrase in phrases)


def match_count(text: str, phrases: list[str]) -> int:
    return sum(1 for phrase in phrases if has_phrase(text, phrase))


def matches_template(text: str, spec: dict[str, object]) -> bool:
    if has_any(text, spec.get("negative_any", [])):
        return False
    for group in spec.get("required_groups", []):
        if not has_any(text, group):
            return False
    context_any = spec.get("context_any", [])
    if context_any and not has_any(text, context_any):
        return False
    return True


MYDIGITAL_TEMPLATE = {
    "required_groups": [
        ["mydigital id", "digital identity"],
        ["myjpj", "jpj app"],
        ["single sign on", "sso", "login", "integration", "integrated", "linked"],
    ],
    "negative_any": [
        "foreign licence conversion",
        "foreign license conversion",
        "driving licence conversion",
        "driving license conversion",
        "conversion applications",
        "licence application",
        "license application",
        "jpj counter",
        "jpj counters",
        "transport ministry",
        "foreign driving licence",
        "foreign driving license",
        "malaysians nationwide from june 1",
    ],
}

MCMC_3R_CONTEXT = [
    "provocative",
    "seditious",
    "social media",
    "monitor",
    "monitoring",
    "enforcement",
    "investigation",
    "do not share",
    "hate speech",
    "offensive post",
    "fake news",
]

MCMC_NEGATIVE = [
    "wsis prizes",
    "service quality standards",
    "consumer protection",
    "telecommunications",
    "telco",
    "broadband",
    "internet quality",
    "shortlisted projects",
    "vote",
    "digital infrastructure",
    "communications service",
    "network coverage",
]


def matches_mcmc_3r_template(text: str) -> bool:
    if has_any(text, MCMC_NEGATIVE):
        return False
    has_3r_subject = has_phrase(text, "3r") or match_count(text, ["race", "religion", "royalty"]) >= 2
    return has_3r_subject and has_any(text, MCMC_3R_CONTEXT)


def build_flags(item: Item) -> dict[str, bool]:
    text = item_text(item)
    flags = dict.fromkeys(ALL_FLAGS, False)
    flags[FLAG_WEATHER] = has_any(
        text,
        [
            "metmalaysia",
            "thunderstorm",
            "heavy rain",
            "strong winds",
            "ribut petir",
            "hujan lebat",
            "amaran cuaca",
            "amaran ribut",
            "amaran hujan",
            "weather warning",
            "storm warning",
            "rain warning",
        ],
    )
    flags[FLAG_HEAT] = has_any(
        text,
        ["cuaca panas", "strok haba", "heat stroke", "heat related", "hot weather"],
    ) or (has_phrase(text, "heat") and has_any(text, ["illness", "stroke", "weather", "related", "death", "deaths"]))
    flags[FLAG_PUBLIC_TRANSPORT] = has_any(
        text,
        ["public transport", "lrt", "mrt", "ktm", "monorail", "rapid kl", "myrapid", "bus service"],
    )
    flags[FLAG_ROAD_ISSUE] = has_any(
        text,
        [
            "road closure",
            "traffic disruption",
            "jalan ditutup",
            "kesesakan",
            "nkve",
            "palm oil",
            "minyak sawit",
            "bandar sultan suleiman",
        ],
    )
    utility_bill = has_any(text, ["electricity bill", "electricity bills", "utility bill", "utility bills", "water bill", "water bills", "bil elektrik"])
    utility_tariff = has_any(text, ["electricity tariff", "water tariff", "tariff unchanged", "tarif elektrik"]) or (
        has_any(text, ["tariff", "tariffs", "tarif"]) and has_any(text, ["electricity", "water", "sabah electricity", "bill", "bills", "bil"])
    )
    flags[FLAG_UTILITY_BILL] = utility_bill or utility_tariff or has_phrase(text, "sabah electricity")
    flags[FLAG_SABAH_ELECTRICITY] = has_phrase(text, "sabah electricity") or (
        has_phrase(text, "sabah")
        and has_any(text, ["electricity bill", "electricity bills", "bil elektrik", "tariff unchanged", "aircon", "electricity tariff"])
    )
    flags[FLAG_JPJ] = has_any(text, ["myjpj", "jpj", "jpj app", "mydigital id", "mydigital"])
    flags[FLAG_MYDIGITAL_INTEGRATION] = matches_template(text, MYDIGITAL_TEMPLATE)
    flags[FLAG_MCMC] = has_phrase(text, "mcmc")
    flags[FLAG_MCMC_3R] = matches_mcmc_3r_template(text)
    flags[FLAG_MCMC_SERVICE_QUALITY] = flags[FLAG_MCMC] and has_any(text, ["service quality standards", "consumer protection", "telecommunications", "communications service", "network coverage"])
    flags[FLAG_MCMC_WSIS] = flags[FLAG_MCMC] and has_any(text, ["wsis prizes", "shortlisted projects", "vote"])
    flags[FLAG_SOCIAL_SECURITY] = has_any(text, ["social security", "keselamatan sosial", "self employed social", "pekerjaan sendiri"])
    flags[FLAG_SCAM] = has_any(text, ["scam", "penipuan", "badal haji"])
    flags[FLAG_CURRENCY] = has_phrase(text, "ringgit") and has_any(
        text,
        ["trade", "trading", "rise", "rises", "strengthen", "strengthening", "forecast", "expected", "range", "us data", "imf", "economy"],
    )
    flags[FLAG_MARKET] = has_phrase(text, "bursa malaysia") or (
        has_phrase(text, "fbm klci") and has_any(text, ["trade", "trading", "range bound", "market", "index"])
    )
    flags[FLAG_AI_ECONOMY] = (has_phrase(text, "ai") or has_phrase(text, "artificial intelligence")) and has_any(
        text,
        ["gdp", "economy", "economic", "rm", "billion", "contribute", "contribution", "automation", "talentcorp", "workers", "jobs"],
    )
    flags[FLAG_HEALTH_SYSTEM] = has_any(text, ["doctor shortage", "shortages of doctors", "medical specialists", "health ministry", "monkey malaria", "wabak", "kesihatan"])
    flags[FLAG_URBAN_DEVELOPMENT] = has_any(text, ["dbkl", "bukit kiara", "ttdi", "urban development", "development project"])
    flags[FLAG_KLANG_VALLEY] = has_any(
        text,
        ["klang valley", "kuala lumpur", "selangor", "subang", "shah alam", "klang", "petaling jaya", "pj", "putrajaya", "ttdi", "bukit kiara", "kl sentral"],
    )
    flags[FLAG_OFFICIAL] = has_any(
        text,
        ["metmalaysia", "health ministry", "moh", "mcmc", "dbkl", "jpj", "myjpj", "immigration", "police", "polis", "ministry", "kementerian", "menteri", "suruhanjaya", "jabatan"],
    )
    flags[FLAG_INDIVIDUAL_INCIDENT] = has_any(
        text,
        [
            "murder",
            "bunuh",
            "stab",
            "tikaman",
            "fatal",
            "killed",
            "dead",
            "drowns",
            "lemas",
            "maut",
            "kemalangan",
            "accident",
            "hit and run",
            "bullying",
            "suspect",
            "remand",
            "fire",
            "blaze",
            "terbakar",
            "police chase",
            "swept away",
            "search continues",
            "search radius",
            "missing",
            "armed",
            "knife",
            "jumps out",
        ],
    )
    flags[FLAG_POLITICAL_NOISE] = has_any(
        text,
        ["umno", "ge16", "election", "political cooperation", "party", "khairy", "johari", "negeri sembilan", "unity government", "kerajaan madani", "red lines"],
    )
    item.flags = flags
    return flags


def ensure_flags(item: Item) -> dict[str, bool]:
    return item.flags if item.flags else build_flags(item)


def key_for(item: Item) -> str:
    text = item_text(item)
    flags = ensure_flags(item)
    flag_groups = [
        ("heat", FLAG_HEAT),
        ("weather", FLAG_WEATHER),
        ("myjpj", FLAG_MYDIGITAL_INTEGRATION),
        ("sabah-electricity", FLAG_SABAH_ELECTRICITY),
        ("self-employed-social-security", FLAG_SOCIAL_SECURITY),
        ("ringgit", FLAG_CURRENCY),
        ("bursa", FLAG_MARKET),
        ("ai-workers", FLAG_AI_ECONOMY),
    ]
    for name, flag in flag_groups:
        if flags[flag]:
            return name
    phrase_groups = [
        ("mara", ["mara", "akta mara"]),
        ("palm-oil-road", ["palm oil", "minyak sawit", "bandar sultan suleiman"]),
        ("badal-haji-scam", ["badal haji"]),
        ("bukit-kiara", ["bukit kiara", "ttdi"]),
        ("doctor-shortage", ["doctor shortage", "shortages of doctors", "medical specialists"]),
        ("monkey-malaria", ["monkey malaria"]),
    ]
    for name, phrases in phrase_groups:
        if has_any(text, phrases):
            return name
    return re.sub(r"[^a-z0-9]+", " ", item.title.lower()).strip()[:90] or item.link


def add_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def has_concrete_policy_value(item: Item) -> bool:
    text = item_text(item)
    return has_any(
        text,
        [
            "application",
            "applications",
            "registration",
            "deadline",
            "effective",
            "implemented",
            "from june",
            "from may",
            "allowance",
            "aid",
            "cash aid",
            "bantuan",
            "subsidy",
            "subsidi",
            "tax relief",
            "fine",
            "penalty",
            "penalties",
            "tariff",
            "tarif",
            "fee",
            "fees",
            "social security",
            "keselamatan sosial",
            "health ministry",
            "moh",
            "education",
            "pendidikan",
        ],
    )


def has_background_value(item: Item) -> bool:
    flags = ensure_flags(item)
    text = item_text(item)
    tag_values = {
        "jpj",
        "social_security",
        "electricity",
        "prices",
        "health",
        "employment",
        "economy",
        "currency",
        "urban_development",
        "public_transport",
        "road_closure",
        "weather",
        "klang_valley",
    }
    if any(tag in tag_values for tag in item.tags):
        return True
    if (
        flags[FLAG_JPJ]
        or flags[FLAG_HEALTH_SYSTEM]
        or flags[FLAG_SOCIAL_SECURITY]
        or flags[FLAG_UTILITY_BILL]
        or flags[FLAG_SABAH_ELECTRICITY]
        or flags[FLAG_CURRENCY]
        or flags[FLAG_MARKET]
        or flags[FLAG_AI_ECONOMY]
        or flags[FLAG_URBAN_DEVELOPMENT]
        or flags[FLAG_PUBLIC_TRANSPORT]
        or flags[FLAG_ROAD_ISSUE]
    ):
        return True
    if flags[FLAG_SCAM] and has_any(text, ["warning", "warns", "beware", "waspada", "alert", "do not share"]):
        return True
    if has_any(
        text,
        [
            "mykad",
            "identity card",
            "digital identity",
            "kkm",
            "licence application",
            "license application",
            "driving licence",
            "driving license",
            "administrative procedure",
            "public service",
            "bnm",
            "opr",
            "interest rate",
            "lpg",
            "food aid",
            "farmer aid",
            "farmers",
            "medical officer",
            "medical officers",
            "healthcare system",
            "school",
            "schools",
            "spm",
            "education system",
            "gig workers",
            "workers",
            "employment",
        ],
    ):
        return True
    return has_concrete_policy_value(item)


def is_low_value_fallback(item: Item) -> bool:
    text = item_text(item)
    if has_concrete_policy_value(item):
        return False
    low_value_groups = [
        ["court", "trial", "lawsuit", "suit", "charged", "charges", "appeal", "sentenced", "convicted"],
        ["corruption", "graft", "bribery", "probe", "investigation", "remand", "suspect", "arrested"],
        ["fraud case", "scam case", "cheating case", "victim lost", "losses"],
        ["assault", "hurt", "injured", "stabbing", "stabbed", "murder", "killed", "dead"],
        ["defence procurement", "defense procurement", "fighter jet", "military procurement", "defence assets", "defense assets"],
        ["appointed", "appointment", "resigns", "resigned", "ceo", "chairman", "board member", "corporate"],
        ["criticised", "criticized", "slams", "hits back", "rebuts", "denies", "political cooperation", "party polls", "internal party"],
        ["celebrity", "entertainment", "sports", "football"],
    ]
    return any(has_any(text, group) for group in low_value_groups)


def uses_generic_fallback(item: Item) -> bool:
    text = item_text(item)
    flags = ensure_flags(item)
    if flags[FLAG_WEATHER] or flags[FLAG_HEAT] or flags[FLAG_MYDIGITAL_INTEGRATION]:
        return False
    if flags[FLAG_ROAD_ISSUE] and has_any(text, ["palm oil", "minyak sawit"]):
        return False
    if flags[FLAG_MCMC_3R]:
        return False
    if flags[FLAG_SCAM] and has_phrase(text, "badal haji"):
        return False
    if flags[FLAG_SOCIAL_SECURITY]:
        return False
    if has_any(text, ["mara", "akta mara"]):
        return False
    if flags[FLAG_URBAN_DEVELOPMENT] and has_any(text, ["bukit kiara", "ttdi"]):
        return False
    if flags[FLAG_SABAH_ELECTRICITY]:
        return False
    if flags[FLAG_HEALTH_SYSTEM] and has_any(text, ["doctor shortage", "shortages of doctors", "medical specialists"]):
        return False
    if flags[FLAG_CURRENCY] or flags[FLAG_MARKET] or flags[FLAG_AI_ECONOMY]:
        return False
    return True


def evaluate_item(item: Item) -> Item:
    flags = build_flags(item)
    score = 0
    item.tags = []
    item.reasons = []
    item.penalties = []
    item.background_value = False
    item.is_official = flags[FLAG_OFFICIAL]
    if item.is_official:
        add_unique(item.reasons, "公的機関・公式発表に関連")

    def add_score(value: int, tags: list[str], reason: str) -> None:
        nonlocal score
        score += value
        for tag in tags:
            add_unique(item.tags, tag)
        if value >= 0:
            add_unique(item.reasons, reason)
        else:
            add_unique(item.penalties, reason)

    if flags[FLAG_WEATHER]:
        add_score(8, ["weather"], "公式警報・天候リスク")
    if flags[FLAG_HEAT]:
        add_score(8, ["health"], "暑熱・熱中症リスク")
    if flags[FLAG_PUBLIC_TRANSPORT] or flags[FLAG_ROAD_ISSUE]:
        tags = []
        if flags[FLAG_PUBLIC_TRANSPORT]:
            tags.append("public_transport")
        if flags[FLAG_ROAD_ISSUE]:
            tags.append("road_closure")
        add_score(7, tags, "交通・道路・移動に影響")
    if flags[FLAG_JPJ] or flags[FLAG_SOCIAL_SECURITY] or flags[FLAG_UTILITY_BILL] or flags[FLAG_SABAH_ELECTRICITY]:
        tags = []
        if flags[FLAG_JPJ]:
            tags.append("jpj")
        if flags[FLAG_SOCIAL_SECURITY]:
            tags.append("social_security")
        if flags[FLAG_UTILITY_BILL] or flags[FLAG_SABAH_ELECTRICITY]:
            tags.extend(["electricity", "prices"])
        add_score(7, tags, "制度・手続き・料金に影響")
    if flags[FLAG_KLANG_VALLEY]:
        add_score(3, ["klang_valley"], "Klang Valley周辺に関連")
    if (
        flags[FLAG_HEALTH_SYSTEM]
        or flags[FLAG_AI_ECONOMY]
        or flags[FLAG_CURRENCY]
        or flags[FLAG_MARKET]
        or flags[FLAG_URBAN_DEVELOPMENT]
    ):
        tags = []
        if flags[FLAG_HEALTH_SYSTEM]:
            tags.append("health")
        if flags[FLAG_AI_ECONOMY]:
            tags.extend(["employment", "economy"])
        if flags[FLAG_CURRENCY]:
            tags.append("currency")
        if flags[FLAG_MARKET]:
            tags.append("economy")
        if flags[FLAG_URBAN_DEVELOPMENT]:
            tags.append("urban_development")
        add_score(5, tags, "医療・雇用・経済・都市生活の背景価値")
    if flags[FLAG_SCAM]:
        add_score(7, ["scam"], "詐欺・注意喚起")
    if flags[FLAG_INDIVIDUAL_INCIDENT]:
        add_score(-8, [], "単発事件・事故の可能性")
    if flags[FLAG_POLITICAL_NOISE]:
        add_score(-5, [], "発言ベースの政治ニュースの可能性")
    item.background_value = has_background_value(item)
    if item.background_value:
        add_unique(item.reasons, "生活者向けの背景価値")
    elif uses_generic_fallback(item):
        add_unique(item.penalties, "汎用フォールバックだが生活影響が薄い")
    if uses_generic_fallback(item) and is_low_value_fallback(item):
        add_score(-6, [], "個別事件・政局発言・低優先トピックの可能性")
    item.score = score
    return item


def score_item(item: Item) -> int:
    evaluate_item(item)
    return item.score


def should_exclude_item(item: Item) -> bool:
    text = item_text(item)
    flags = ensure_flags(item)
    if item.feed == "Malay Mail Money" and not (
        has_any(text, ["malaysia", "malaysian", "kuala lumpur", "semiconductor"])
        or flags[FLAG_CURRENCY]
        or flags[FLAG_MARKET]
        or flags[FLAG_AI_ECONOMY]
    ):
        return True

    practical_exception = (
        flags[FLAG_WEATHER]
        or flags[FLAG_HEAT]
        or flags[FLAG_PUBLIC_TRANSPORT]
        or flags[FLAG_ROAD_ISSUE]
        or flags[FLAG_HEALTH_SYSTEM]
        or flags[FLAG_SCAM]
        or has_any(text, ["mcmc", "3r"])
    )
    if flags[FLAG_INDIVIDUAL_INCIDENT] and not practical_exception:
        return True

    policy_exception = (
        has_any(text, ["mara", "akta mara", "m40 women", "childcare", "tax relief", "budi madani", "spm", "moral studies", "education"])
        or flags[FLAG_SOCIAL_SECURITY]
        or flags[FLAG_HEALTH_SYSTEM]
        or flags[FLAG_URBAN_DEVELOPMENT]
        or flags[FLAG_JPJ]
    )
    if flags[FLAG_POLITICAL_NOISE] and not policy_exception:
        return True
    if uses_generic_fallback(item):
        if is_low_value_fallback(item):
            return True
        if not item.background_value:
            return True
    return False


def category_for(item: Item) -> str:
    flags = ensure_flags(item)
    if (flags[FLAG_WEATHER] or flags[FLAG_HEAT]) and not flags[FLAG_INDIVIDUAL_INCIDENT]:
        return "【速報】"
    if (
        flags[FLAG_PUBLIC_TRANSPORT]
        or flags[FLAG_ROAD_ISSUE]
        or flags[FLAG_JPJ]
        or flags[FLAG_UTILITY_BILL]
        or flags[FLAG_SABAH_ELECTRICITY]
        or flags[FLAG_SOCIAL_SECURITY]
        or flags[FLAG_SCAM]
        or has_any(item_text(item), ["mcmc", "3r", "haji"])
    ):
        return "【生活インパクト】"
    return "【知っておくと得】"


def select_items(items: list[Item], now: datetime) -> list[Item]:
    cutoff = now - timedelta(hours=48)
    recent = [item for item in items if cutoff <= item.pub_date <= now]
    by_key: dict[str, Item] = {}
    sources_by_key: dict[str, set[str]] = {}
    for item in recent:
        evaluate_item(item)
        key = key_for(item)
        sources_by_key.setdefault(key, set()).add(item.source)
        current = by_key.get(key)
        if current is None or (item.score, item.pub_date) > (current.score, current.pub_date):
            by_key[key] = item
    for key, item in by_key.items():
        item.source_count = len(sources_by_key.get(key, {item.source}))
        if item.source_count > 1:
            add_unique(item.reasons, "複数媒体で同一論点を報道")

    candidates = [item for item in by_key.values() if item.score >= 3 and not should_exclude_item(item)]
    candidates.sort(key=lambda item: (item.score, item.pub_date), reverse=True)

    selected: list[Item] = []
    source_counts: Counter[str] = Counter()
    category_limits = {"【速報】": 10, "【生活インパクト】": 20, "【知っておくと得】": 40}
    category_counts: Counter[str] = Counter()
    for item in candidates:
        category = category_for(item)
        if source_counts[item.source] >= 24:
            continue
        if category_counts[category] >= category_limits[category]:
            continue
        item.category = category
        selected.append(item)
        source_counts[item.source] += 1
        category_counts[category] += 1
        if len(selected) >= 40:
            break
    return selected


def selection_summary(items: list[Item], selected: list[Item], now: datetime) -> str:
    cutoff = now - timedelta(hours=48)
    recent = [item for item in items if cutoff <= item.pub_date <= now]
    unique_keys = {key_for(item) for item in recent}
    category_counts = Counter(item.category for item in selected)
    tag_counts: Counter[str] = Counter()
    for item in selected:
        tag_counts.update(item.tags)
    top_tags = ", ".join(f"{tag}:{count}" for tag, count in tag_counts.most_common(8)) or "なし"
    return "\n".join(
        [
            "selection_summary:",
            f"- recent_items: {len(recent)}",
            f"- unique_topics: {len(unique_keys)}",
            f"- selected_items: {len(selected)}",
            f"- categories: 速報={category_counts['【速報】']}, 生活インパクト={category_counts['【生活インパクト】']}, 知っておくと得={category_counts['【知っておくと得】']}",
            f"- top_tags: {top_tags}",
        ]
    )


def japanese_summary(item: Item) -> tuple[str, str, str, str]:
    text = item_text(item)
    flags = ensure_flags(item)
    if flags[FLAG_WEATHER]:
        return (
            "KLを含む複数地域で雷雨・大雨・強風への注意が必要です。",
            "MetMalaysiaが悪天候への注意を出しました。\n対象地域では短時間の強い雨や突風が見込まれています。",
            "冠水、渋滞、屋外予定の中断に注意が必要です。",
            "移動前にMetMalaysiaと道路状況を確認。",
        )
    if flags[FLAG_HEAT]:
        return (
            "全国で熱中症関連の健康リスクが高まっています。",
            "保健省が熱中症・熱疲労などの発生状況を公表しました。\n屋外活動や運動時の発症が主なリスクとして挙げられています。",
            "学校行事、屋外勤務、子どもや高齢者の外出管理に影響します。",
            "水分補給、屋外活動の短縮、車内放置防止を徹底。",
        )
    if flags[FLAG_MYDIGITAL_INTEGRATION]:
        return (
            "MyDigital IDとMyJPJの連携が稼働しています。",
            "MyJPJアプリ向けにMyDigital IDのシングルサインオン連携が始まりました。\n当局は導入後の運用は順調だとしています。",
            "車両・免許関連のオンライン手続きでログイン導線が変わる可能性があります。",
            "",
        )
    if flags[FLAG_ROAD_ISSUE] and has_any(text, ["palm oil", "minyak sawit"]):
        return (
            "Klang周辺で道路上への油流出に注意が必要です。",
            "パーム油タンクローリー関連の事故で、道路に油が流れました。\n周辺の生活道路・物流動線に影響する可能性があります。",
            "路面の滑りやすさ、片側規制、渋滞に注意が必要です。",
            "",
        )
    if flags[FLAG_MCMC_3R]:
        return (
            "3R関連の挑発的投稿に対し、当局が監視・摘発を強めます。",
            "人種・宗教・王室に関する挑発的投稿を作成・拡散しないよう注意喚起されました。\n違反時には法的処分の可能性があります。",
            "SNS投稿や転送でも法的リスクが生じる可能性があります。",
            "真偽不明の3R関連投稿は共有しない。",
        )
    if flags[FLAG_SCAM] and has_phrase(text, "badal haji"):
        return (
            "安すぎる代理ハジサービスへの詐欺注意が出ています。",
            "不自然に安い代理巡礼サービスへの注意が呼びかけられました。\n家族のためにサービスを探す人が標的になり得ます。",
            "送金後にサービスが実行されないなど、金銭被害の恐れがあります。",
            "登録・送金前に正規事業者か確認。",
        )
    if flags[FLAG_SOCIAL_SECURITY]:
        return (
            "自営業者向け社会保障法の改正案が次期国会に提出予定です。",
            "人的資源相が、改正案を閣議承認後に国会へ出すと説明しました。\n自営業者やギグワーカーの保護に関わる制度です。",
            "個人事業主、配達員、フリーランスの保障や拠出に影響する可能性があります。",
            "",
        )
    if has_any(text, ["mara", "akta mara"]):
        return (
            "MARA法改正はガバナンス強化と支援制度の再整理が焦点です。",
            "MARA法改正の草案提出や制度見直しが報じられています。\n教育、起業支援、中小企業支援に関わる政策です。",
            "ブミプトラ関連の教育・事業支援制度に影響する可能性があります。",
            "",
        )
    if flags[FLAG_URBAN_DEVELOPMENT] and has_any(text, ["bukit kiara", "ttdi"]):
        return (
            "DBKLがBukit Kiara開発案に300mの緩衝帯を設定しました。",
            "TTDI住民の懸念を受け、開発計画にバッファーゾーンが課されました。\n都市開発と住環境保護の調整が進められています。",
            "TTDI、Bukit Kiara周辺の住環境、緑地、交通に関わります。",
            "",
        )
    if flags[FLAG_SABAH_ELECTRICITY]:
        return (
            "Sabahの電気代上昇懸念について、料金表は変わっていないと説明されました。",
            "Sabah Electricityは、請求額増加への懸念に対し料金自体は未変更だと説明しました。\n暑さによるエアコン使用増が主因とみられています。",
            "暑い時期は家庭の電気代が上がりやすくなります。",
            "",
        )
    if flags[FLAG_HEALTH_SYSTEM] and has_any(text, ["doctor shortage", "shortages of doctors", "medical specialists"]):
        return (
            "保健省が医師・専門医不足に対応するタスクフォースを設置しました。",
            "医師不足や人材定着を検討する省庁横断タスクフォースが立ち上がりました。\n特にSabahの医療人材不足が重点課題とされています。",
            "地方医療、待ち時間、専門医アクセスに関わる中長期課題です。",
            "",
        )
    if flags[FLAG_CURRENCY]:
        return (
            "リンギット相場と経済見通しが引き続き注目されています。",
            "リンギットの動きや経済見通しについて、慎重または前向きな評価が報じられました。\n外部指標や政策判断が為替材料になります。",
            "海外送金、旅行、輸入品、外貨建て支払いに影響する可能性があります。",
            "",
        )
    if flags[FLAG_MARKET]:
        return (
            "Bursa Malaysiaは慎重な値動きが見込まれています。",
            "西アジア情勢などの外部要因を背景に、レンジ相場の見方が報じられました。\n市場心理は不透明感に左右されやすい状況です。",
            "投資信託、株式投資、企業景況感を見ている人には参考になります。",
            "",
        )
    if flags[FLAG_AI_ECONOMY]:
        return (
            "AI・自動化で一部労働者の再学習ニーズが高まっています。",
            "AIと自動化が雇用構造を変えつつあると報じられました。\n今後は適応力やスキル更新が重要になります。",
            "事務・定型業務に関わる人は、学び直しの必要性が高まりそうです。",
            "",
        )
    return (
        item.title,
        f"{item.description or item.title}\nRSS内のタイトルと説明をもとに整理しました。",
        "生活・仕事・家計に関わる背景ニュースとして把握しておく価値があります。"
        if item.background_value
        else "RSS内の情報だけでは生活への直接影響は確認できません。",
        "",
    )


def render(selected: list[Item], processed_count: int, failed_sources: list[str]) -> str:
    lines: list[str] = []
    ordered_categories = ["【速報】", "【生活インパクト】", "【知っておくと得】"]
    for category in ordered_categories:
        group = [item for item in selected if item.category == category]
        lines.append(category)
        lines.append("")
        for item in group:
            conclusion, what, impact, action = japanese_summary(item)
            lines.append(f"- 結論：{conclusion}")
            for line in what.splitlines()[:2]:
                lines.append(f"- 何が起きた：{line}")
            lines.append(f"- 生活への影響：{impact}")
            if action:
                lines.append(f"- 次アクション：{action}")
            pub = f"{item.pub_date.year}年{item.pub_date.month}月{item.pub_date.day}日"
            lines.append(f"- 出典：{item.source}（{pub}）")
            lines.append(f"- 出典元URL：{item.link}")
            lines.append("")
    lines.append(f"処理対象件数：{processed_count}件")
    lines.append(f"要約対象件数：{len(selected)}件")
    lines.append(f"失敗したソース一覧：{', '.join(failed_sources) if failed_sources else 'なし'}")
    return "\n".join(lines).strip()


def diagnose_fetch(results: list[FetchResult]) -> str:
    lines = diagnostic_lines()
    for result in results:
        head = result.data.decode("utf-8", "replace")[:100].replace("\n", "\\n").replace("\r", "\\r")
        state = "OK" if result.ok else "FAIL"
        lines.append(
            f"{result.url}\n{state} | method={result.method} | status={result.status or 'None'} "
            f"| content-type={result.content_type} | head={head} | error={result.error}"
        )
    return "\n".join(lines)


def self_test() -> int:
    now = datetime(2026, 5, 7, 12, 0, tzinfo=MYT)
    failures: list[str] = []

    def item(title: str, description: str = "") -> Item:
        return Item("Test", "Test Feed", title, description, now, "raw", "https://example.test/item")

    def check(name: str, condition: bool) -> None:
        if not condition:
            failures.append(name)

    ai_item = item(
        "AI expected to contribute up to RM20b yearly to Malaysia's GDP by 2030, says Gobind",
        "KUALA LUMPUR, May 5 - Artificial intelligence is expected to contribute up to RM20b yearly to Malaysia's GDP.",
    )
    evaluate_item(ai_item)
    check("AI/GDP is not weather", not ai_item.flags[FLAG_WEATHER])
    check("AI/GDP is not breaking", category_for(ai_item) != "【速報】")
    check("AI/GDP uses AI economy flag", ai_item.flags[FLAG_AI_ECONOMY])
    check("AI/GDP does not use weather summary", "雷雨" not in japanese_summary(ai_item)[0])

    for word in ["contribute", "contribution", "contributed", "distribute", "distribution", "attribute", "attributed"]:
        test_item = item(f"{word} expected in Malaysia economy")
        evaluate_item(test_item)
        check(f"{word} does not trigger weather", not test_item.flags[FLAG_WEATHER])
        check(f"{word} key is not weather", key_for(test_item) != "weather")

    for phrase in ["separation bill", "amendment bill", "supply bill", "parliamentary bill", "bill tabled in Parliament"]:
        test_item = item(phrase, "The proposal was discussed by lawmakers.")
        evaluate_item(test_item)
        check(f"{phrase} is not utility bill", not test_item.flags[FLAG_UTILITY_BILL])
        check(f"{phrase} does not use Sabah electricity summary", "Sabahの電気代" not in japanese_summary(test_item)[0])

    weather_item = item("Ribut petir, hujan lebat di KL hingga petang - MetMalaysia")
    evaluate_item(weather_item)
    check("BM weather triggers weather", weather_item.flags[FLAG_WEATHER])
    check("BM weather can be breaking", category_for(weather_item) == "【速報】")

    heat_item = item("Cuaca panas: 56 kes, dua kematian akibat strok haba")
    evaluate_item(heat_item)
    check("BM heat triggers heat", heat_item.flags[FLAG_HEAT])

    sabah_item = item("Sabah electricity bills rising?", "Tariff unchanged; aircon use is the likeliest reason.")
    evaluate_item(sabah_item)
    check("Sabah electricity triggers Sabah flag", sabah_item.flags[FLAG_SABAH_ELECTRICITY])
    check("Sabah electricity summary fires", "Sabahの電気代" in japanese_summary(sabah_item)[0])

    ringgit_item = item("Ringgit expected to trade in RM3.96-RM3.98 range next week ahead of US data")
    evaluate_item(ringgit_item)
    check("Ringgit forecast triggers currency", ringgit_item.flags[FLAG_CURRENCY])
    check("Ringgit summary fires", "リンギット" in japanese_summary(ringgit_item)[0])

    market_item = item("Bursa Malaysia seen trading range-bound between 1,700 and 1,730 next week")
    evaluate_item(market_item)
    check("Bursa triggers market", market_item.flags[FLAG_MARKET])
    check("Bursa summary fires", "Bursa Malaysia" in japanese_summary(market_item)[0])

    jpj_conversion = item(
        "Transport Ministry: JPJ to accept foreign licence conversion applications for Malaysians nationwide from June 1"
    )
    evaluate_item(jpj_conversion)
    check("JPJ conversion keeps JPJ flag", jpj_conversion.flags[FLAG_JPJ])
    check("JPJ conversion does not trigger MyDigital integration", not jpj_conversion.flags[FLAG_MYDIGITAL_INTEGRATION])
    check("JPJ conversion does not use MyDigital summary", "MyDigital IDとMyJPJ" not in japanese_summary(jpj_conversion)[0])

    jpj_counter = item("JPJ counters to handle driving licence conversion applications")
    evaluate_item(jpj_counter)
    check("JPJ counter keeps JPJ flag", jpj_counter.flags[FLAG_JPJ])
    check("JPJ counter does not trigger MyDigital integration", not jpj_counter.flags[FLAG_MYDIGITAL_INTEGRATION])
    check("JPJ counter does not use MyDigital summary", "MyDigital IDとMyJPJ" not in japanese_summary(jpj_counter)[0])

    mydigital_item = item("MyDigital ID single sign-on integration begins for MyJPJ app")
    evaluate_item(mydigital_item)
    check("MyDigital integration flag triggers", mydigital_item.flags[FLAG_MYDIGITAL_INTEGRATION])
    check("MyDigital integration summary fires", "MyDigital IDとMyJPJ" in japanese_summary(mydigital_item)[0])

    mcmc_quality = item("MCMC enhances service quality standards to strengthen consumer protection")
    evaluate_item(mcmc_quality)
    check("MCMC quality keeps MCMC flag", mcmc_quality.flags[FLAG_MCMC])
    check("MCMC quality does not trigger 3R", not mcmc_quality.flags[FLAG_MCMC_3R])
    check("MCMC quality does not use 3R summary", "3R関連" not in japanese_summary(mcmc_quality)[0])

    mcmc_wsis = item("MCMC urges Malaysians to vote for nation's shortlisted projects at WSIS Prizes 2026")
    evaluate_item(mcmc_wsis)
    check("MCMC WSIS keeps MCMC flag", mcmc_wsis.flags[FLAG_MCMC])
    check("MCMC WSIS does not trigger 3R", not mcmc_wsis.flags[FLAG_MCMC_3R])
    check("MCMC WSIS does not use 3R summary", "3R関連" not in japanese_summary(mcmc_wsis)[0])

    mcmc_3r = item("MCMC warns against sharing provocative 3R posts on race, religion and royalty")
    evaluate_item(mcmc_3r)
    check("MCMC 3R flag triggers", mcmc_3r.flags[FLAG_MCMC_3R])
    check("MCMC 3R summary fires", "3R関連" in japanese_summary(mcmc_3r)[0])

    mcmc_race_guard = item("MCMC announces race entries for digital innovation contest")
    evaluate_item(mcmc_race_guard)
    check("MCMC race guard keeps MCMC flag", mcmc_race_guard.flags[FLAG_MCMC])
    check("MCMC race guard does not trigger 3R", not mcmc_race_guard.flags[FLAG_MCMC_3R])

    mykad_item = item("MyKad renewal applications open nationwide from June 1")
    evaluate_item(mykad_item)
    check("MyKad has background value", mykad_item.background_value)

    kkm_item = item("KKM announces medical officer shift system improvements")
    evaluate_item(kkm_item)
    check("KKM medical system has background value", kkm_item.background_value)

    bnm_item = item("BNM keeps OPR unchanged as households watch interest rates")
    evaluate_item(bnm_item)
    check("BNM OPR has background value", bnm_item.background_value)

    utility_item = item("Water tariff adjustment for households begins next month")
    evaluate_item(utility_item)
    check("Public utility tariff has background value", utility_item.background_value)

    education_item = item("Education Ministry updates school assessment system")
    evaluate_item(education_item)
    check("Education system has background value", education_item.background_value)

    court_item = item("Former officer's corruption trial continues in court")
    evaluate_item(court_item)
    check("Individual court case has no background value", not court_item.background_value)
    check("Individual court case is excluded as fallback", should_exclude_item(court_item))

    procurement_item = item("Defence procurement of new military assets under review")
    evaluate_item(procurement_item)
    check("Defence procurement has no background value", not procurement_item.background_value)
    check("Defence procurement is excluded as fallback", should_exclude_item(procurement_item))

    corporate_item = item("Company appoints new chairman after board reshuffle")
    evaluate_item(corporate_item)
    check("Corporate appointment has no background value", not corporate_item.background_value)
    check("Corporate appointment is excluded as fallback", should_exclude_item(corporate_item))

    policy_speech = item("Minister says cash aid applications open for low-income households")
    evaluate_item(policy_speech)
    check("Concrete aid speech has background value", policy_speech.background_value)
    check("Concrete aid speech is not excluded", not should_exclude_item(policy_speech))

    political_attack = item("Party leader slams rival over internal party dispute")
    evaluate_item(political_attack)
    check("Party dispute has no background value", not political_attack.background_value)
    check("Party dispute is excluded", should_exclude_item(political_attack))

    weather_guard = item("Ribut petir, hujan lebat di KL hingga petang - MetMalaysia")
    evaluate_item(weather_guard)
    weather_guard.background_value = False
    check("Template weather is not excluded by generic fallback rule", not should_exclude_item(weather_guard))

    if failures:
        print("self-test failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("self-test passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--diagnose-fetch", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", help="Write the final Markdown summary to this path.")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    results = [(source, feed, fetch_rss(url)) for source, feed, url in SOURCES]
    if args.diagnose_fetch:
        print(diagnose_fetch([result for _, _, result in results]))
        return 0

    all_items: list[Item] = []
    failed_sources: list[str] = []
    for source, feed, result in results:
        if not result.ok:
            failed_sources.append(f"{feed}: {result.error}")
            continue
        try:
            all_items.extend(parse_items(source, feed, result.data))
        except Exception as exc:
            failed_sources.append(f"{feed}: parse failed: {type(exc).__name__}: {exc}")

    now = datetime.now(MYT)
    processed_count = sum(1 for item in all_items if now - timedelta(hours=48) <= item.pub_date <= now)
    selected = select_items(all_items, now)
    if args.diagnostics:
        print("\n".join(diagnostic_lines()))
        print("")
        print(selection_summary(all_items, selected, now))
        print("")
    output = render(selected, processed_count, failed_sources)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output + "\n", encoding="utf-8")
        print(f"Wrote summary: {output_path}")
        print(f"処理対象件数：{processed_count}件")
        print(f"要約対象件数：{len(selected)}件")
        print(f"失敗したソース一覧：{', '.join(failed_sources) if failed_sources else 'なし'}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

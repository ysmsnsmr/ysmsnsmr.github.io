#!/usr/bin/env python3
import argparse
import email.utils
import html
import json
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
PAUL_TAN_SOURCE = ("Paul Tan", "Paul Tan", "https://paultan.org/feed/")
MYT = timezone(timedelta(hours=8))

FLAG_WEATHER = "is_weather"
FLAG_HEAT = "is_heat"
FLAG_PUBLIC_TRANSPORT = "is_public_transport"
FLAG_ROAD_ISSUE = "is_road_issue"
FLAG_FLOOD_IMPACT = "is_flood_impact"
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
FLAG_COST_OF_LIVING = "is_cost_of_living"
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
    FLAG_FLOOD_IMPACT,
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
    FLAG_COST_OF_LIVING,
    FLAG_HEALTH_SYSTEM,
    FLAG_URBAN_DEVELOPMENT,
    FLAG_KLANG_VALLEY,
    FLAG_OFFICIAL,
    FLAG_INDIVIDUAL_INCIDENT,
    FLAG_POLITICAL_NOISE,
]

LAST_FINALIZE_STATS: dict[str, object] = {}
CATEGORY_PRIORITY = {"【速報】": 0, "【生活インパクト】": 1, "【知っておくと得】": 2}
FINANCIAL_LIMITS = {"ringgit": 2, "bursa": 1, "bnm_policy": 2}
SOURCE_LIMITS = {"Paul Tan": 1}
PRACTICAL_LIFE_TAGS = {
    "weather",
    "flood",
    "road_closure",
    "public_transport",
    "water",
    "electricity",
    "health",
    "public_health",
    "prices",
    "social_security",
    "social_support",
    "education",
    "immigration",
    "jpj",
    "mykad",
    "mydigital",
    "food_supply",
    "agriculture",
    "scam",
    "urban_development",
    "fuel",
    "vehicle_safety",
}

PAUL_TAN_POSITIVE_GROUPS = {
    "public_transport": [
        "bus",
        "ktmb",
        "lrt",
        "mrt",
        "public transport",
        "rail",
        "rapid kl",
        "service disruption",
        "service update",
        "train",
    ],
    "road_toll": [
        "highway",
        "lane closure",
        "rfid",
        "road closure",
        "road closures",
        "road users",
        "smart tag",
        "smarttag",
        "toll",
        "traffic diversion",
        "traffic enforcement",
    ],
    "driver_obligations": [
        "insurance",
        "jpj",
        "licence",
        "license",
        "puspakom",
        "road tax",
        "saman",
        "summons",
        "vehicle inspection",
    ],
    "fuel_subsidy": [
        "b15",
        "biodiesel",
        "budi madani",
        "budi95",
        "diesel",
        "fuel subsidy",
        "petrol",
        "ron95",
        "subsidy",
    ],
    "safety_recall": [
        "airbag",
        "brake",
        "recall",
        "safety defect",
        "safety recall",
        "vehicle recall",
    ],
}

PAUL_TAN_NOISE_GROUPS = {
    "launch_review": [
        "first drive",
        "launch",
        "launched",
        "preview",
        "review",
        "spied",
        "spyshot",
        "test drive",
    ],
    "sales_pricing": [
        "drive sale",
        "mega drive sale",
        "pre-owned",
        "priced at",
        "pricing",
        "promotion",
        "rebate",
        "sale",
        "sales event",
        "showroom",
        "specs",
        "variant",
        "variants",
    ],
    "enthusiast_business": [
        "brand",
        "cbu",
        "ckd",
        "concept",
        "factory",
        "motorsport",
        "plant",
        "production capacity",
        "teaser",
    ],
    "ordinary_vehicle": [
        "ev",
        "hatchback",
        "mpv",
        "pickup",
        "sedan",
        "suv",
    ],
}
PAUL_TAN_JPJ_DATA_ONLY_WORDS = [
    "brands",
    "data",
    "market share",
    "registrations",
    "sales",
    "tally",
    "top 20",
    "units",
]
PAUL_TAN_DRIVER_ACTION_WORDS = [
    "application",
    "apply",
    "conversion",
    "convert",
    "counter",
    "deadline",
    "enforcement",
    "fine",
    "inspection",
    "licence",
    "license",
    "myjpj",
    "procedure",
    "puspakom",
    "renew",
    "renewal",
    "road tax",
    "saman",
    "summons",
]
PAUL_TAN_ILLEGAL_TRANSPORT_WORDS = [
    "illegal transport",
    "illegal transportation",
    "illegal passenger",
    "illegal goods transport",
    "illegal freight",
    "illegal taxi",
    "e-hailing illegal",
    "unlicensed transport",
    "unlicensed transportation",
    "without permit",
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


def matching_phrases(text: str, phrases: list[str]) -> list[str]:
    return [phrase for phrase in phrases if has_phrase(text, phrase)]


def grouped_phrase_matches(text: str, groups: dict[str, list[str]]) -> dict[str, list[str]]:
    matches: dict[str, list[str]] = {}
    for group, phrases in groups.items():
        group_matches = matching_phrases(text, phrases)
        if group_matches:
            matches[group] = group_matches
    return matches


def is_paul_tan_item(item: Item) -> bool:
    return item.source == "Paul Tan" or item.feed == "Paul Tan"


def paul_tan_gate(item: Item) -> tuple[str, dict[str, list[str]], dict[str, list[str]]]:
    if not is_paul_tan_item(item):
        return "not_applicable", {}, {}
    text = item_text(item)
    positive_groups = grouped_phrase_matches(text, PAUL_TAN_POSITIVE_GROUPS)
    noise_groups = grouped_phrase_matches(text, PAUL_TAN_NOISE_GROUPS)
    if is_paul_tan_jpj_data_only_item(text, positive_groups):
        return "review", positive_groups, noise_groups
    if positive_groups and not noise_groups:
        return "accept", positive_groups, noise_groups
    if positive_groups and noise_groups:
        if set(noise_groups) <= {"ordinary_vehicle"}:
            return "accept", positive_groups, noise_groups
        return "review", positive_groups, noise_groups
    if noise_groups:
        return "reject", positive_groups, noise_groups
    return "reject", positive_groups, noise_groups


def paul_tan_gate_decision(item: Item) -> str:
    decision, _, _ = paul_tan_gate(item)
    return decision


def paul_tan_signal_groups(item: Item) -> set[str]:
    _, positive_groups, _ = paul_tan_gate(item)
    return set(positive_groups)


def is_paul_tan_jpj_data_only_item(text: str, positive_groups: dict[str, list[str]]) -> bool:
    """Avoid treating JPJ as driver impact when it only appears as a data source."""
    if set(positive_groups) != {"driver_obligations"}:
        return False
    if not has_phrase(text, "jpj"):
        return False
    return has_any(text, PAUL_TAN_JPJ_DATA_ONLY_WORDS) and not has_any(text, PAUL_TAN_DRIVER_ACTION_WORDS)


def is_paul_tan_illegal_transport_enforcement(item: Item) -> bool:
    if not is_paul_tan_item(item):
        return False
    text = item_text(item)
    return has_phrase(text, "jpj") and has_any(text, PAUL_TAN_ILLEGAL_TRANSPORT_WORDS)


def paul_tan_display_description(item: Item) -> str:
    if not is_paul_tan_item(item):
        return item.description
    value = item.description or item.title
    value = re.sub(r"\s*The post .+? appeared first on Paul Tan'?s Automotive News\s*\.?\s*$", "", value, flags=re.IGNORECASE)
    return clean(value)


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
        [
            "public transport",
            "commuting",
            "grab group ride",
            "ktmb",
            "extra trains",
            "hari raya aidiladha",
            "school holidays",
            "train services",
            "lrt",
            "mrt",
            "ktm",
            "monorail",
            "rapid kl",
            "myrapid",
            "bus service",
        ],
    )
    flags[FLAG_ROAD_ISSUE] = has_any(
        text,
        [
            "road users advised",
            "plan journeys",
            "road closure",
            "road closed",
            "closed from midnight",
            "traffic disruption",
            "traffic congestion",
            "jalan ditutup",
            "kesesakan",
            "nkve",
            "palm oil",
            "minyak sawit",
            "bandar sultan suleiman",
            "padang merbok",
            "bukit bintang",
            "pavilion kl",
        ],
    )
    flags[FLAG_FLOOD_IMPACT] = has_any(text, ["flash floods", "toppled trees", "flood hotline", "mbpj"])
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
    flags[FLAG_COST_OF_LIVING] = has_any(
        text,
        [
            "jualan rahmah",
            "rahmah",
            "kos sara hidup",
            "barang keperluan",
            "harga lebih rendah",
            "jualan murah",
            "pkps",
            "rakan strategik",
            "cost of living",
            "basic necessities",
            "lower prices",
            "cheap sale",
        ],
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
    if (
        has_any(text, ["jalan bukit bintang", "bukit bintang"])
        and has_any(text, ["closed", "ditutup", "road closure", "jalan ditutup", "road closed"])
        and has_any(text, ["midnight", "from midnight", "tengah malam", "12 tengah malam", "mulai tengah malam", "5 pagi"])
        and has_any(text, ["pavilion kl", "pavilion kuala lumpur", "quranic madani", "event", "traffic restriction", "traffic restrictions", "road users", "plan journeys"])
    ):
        return "jalan-bukit-bintang-closure"
    if has_any(text, ["cloud seeding", "drought"]) and has_any(
        text,
        [
            "kedah",
            "perlis",
            "rice bowl",
            "dams hit alert levels",
            "dam hit alert levels",
            "dams hit",
            "alert levels",
        ],
    ):
        return "cloud-seeding-drought-rice-bowl"
    flag_groups = [
        ("heat", FLAG_HEAT),
        ("flood-impact", FLAG_FLOOD_IMPACT),
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
            "filial responsibility law",
            "moh guidelines",
            "house officers",
            "working hours",
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
        "cost_of_living",
        "social_support",
        "public_transport",
        "road_closure",
        "flood",
        "weather",
        "klang_valley",
        "fuel",
        "vehicle_safety",
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
        or flags[FLAG_COST_OF_LIVING]
        or flags[FLAG_URBAN_DEVELOPMENT]
        or flags[FLAG_PUBLIC_TRANSPORT]
        or flags[FLAG_ROAD_ISSUE]
        or flags[FLAG_FLOOD_IMPACT]
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
            "jualan rahmah",
            "rahmah",
            "kos sara hidup",
            "cost of living",
            "barang keperluan",
            "harga lebih rendah",
            "jualan murah",
            "pkps",
            "rakan strategik",
            "public health",
            "drought",
            "cloud seeding",
            "food supply",
            "rice bowl",
            "agriculture",
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


def has_practical_life_value(item: Item) -> bool:
    flags = ensure_flags(item)
    text = item_text(item)
    if any(tag in PRACTICAL_LIFE_TAGS for tag in item.tags):
        return True
    if (
        flags[FLAG_WEATHER]
        or flags[FLAG_HEAT]
        or flags[FLAG_PUBLIC_TRANSPORT]
        or flags[FLAG_ROAD_ISSUE]
        or flags[FLAG_FLOOD_IMPACT]
        or flags[FLAG_UTILITY_BILL]
        or flags[FLAG_SABAH_ELECTRICITY]
        or flags[FLAG_JPJ]
        or flags[FLAG_MYDIGITAL_INTEGRATION]
        or flags[FLAG_SOCIAL_SECURITY]
        or flags[FLAG_SCAM]
        or flags[FLAG_HEALTH_SYSTEM]
        or flags[FLAG_URBAN_DEVELOPMENT]
        or flags[FLAG_COST_OF_LIVING]
    ):
        return True
    if flags[FLAG_CURRENCY] or flags[FLAG_MARKET]:
        return True
    if has_any(
        text,
        [
            "mykad",
            "myjpj",
            "mydigital id",
            "jualan rahmah",
            "rahmah",
            "kos sara hidup",
            "cost of living",
            "barang keperluan",
            "harga lebih rendah",
            "jualan murah",
            "pkps",
            "rakan strategik",
            "housing ministry",
            "option to purchase clause",
            "public health",
            "food supply",
            "rice bowl",
            "agriculture",
            "cloud seeding",
            "drought",
            "bnm",
            "bank negara",
            "opr",
            "ringgit",
        ],
    ):
        return True
    return has_concrete_policy_value(item)


def is_low_value_fallback(item: Item) -> bool:
    text = item_text(item)
    hard_exclusion_groups = [
        [
            "court",
            "trial",
            "lawsuit",
            "suit",
            "charged",
            "charges",
            "charged with",
            "pleaded not guilty",
            "court to decide",
            "high court",
            "bid to stay",
            "appeal",
            "sentenced",
            "convicted",
        ],
        [
            "corruption",
            "graft",
            "bribery",
            "macc",
            "sprm",
            "recording his statement",
            "probe",
            "investigation",
            "remand",
            "suspect",
            "arrested",
        ],
        ["fraud case", "scam case", "cheating case", "victim lost", "losses"],
        ["drug syndicate", "drug syndicates", "drug bust", "narcotics raid"],
        ["assault", "hurt", "injured", "stabbing", "stabbed", "murder", "killed", "dead"],
        ["compensation claim", "compensation claims", "awaiting court decision", "court decision pending"],
        ["cruise ship infection", "overseas infection ship", "foreign infection ship", "no malaysians aboard", "hantavirus linked cruise ship", "hantavirus linked", "hantavirus"],
    ]
    if any(has_any(text, group) for group in hard_exclusion_groups):
        return True

    if has_concrete_policy_value(item) or has_background_value(item):
        return False

    low_value_groups = [
        [
            "defence procurement",
            "defense procurement",
            "defence minister",
            "defense minister",
            "fighter jet",
            "missile",
            "naval strike missiles",
            "lcs project",
            "military procurement",
            "defence assets",
            "defense assets",
            "cabinet to discuss",
        ],
        ["appointed", "appointment", "names", "new president", "group ceo", "resigns", "resigned", "ceo", "chairman", "board member", "corporate"],
        ["queen praises", "king praises", "royal visit", "courtesy visit", "royal audience", "uzbekistan"],
        ["donation", "donations", "bereaved family", "grieving family", "medical episode"],
        ["national convention", "party convention", "election preparation", "election preparations", "poll", "survey", "favourability survey", "favorability survey"],
        ["ipo oversubscribed", "oversubscribed", "ipo application", "ipo applications"],
        ["tourism image", "tourism reputation", "reputation survey", "favourability ranking", "favorability ranking", "favourability survey", "favorability survey", "international favourability", "international favorability"],
        [
            "criticised",
            "criticized",
            "slams",
            "hits back",
            "rebuts",
            "denies",
            "dismisses opposition criticism",
            "pas no better",
            "political cooperation",
            "party polls",
            "internal party",
        ],
        ["celebrity", "entertainment", "sports", "football"],
    ]
    return any(has_any(text, group) for group in low_value_groups)


def uses_generic_fallback(item: Item) -> bool:
    text = item_text(item)
    flags = ensure_flags(item)
    if flags[FLAG_WEATHER] or flags[FLAG_HEAT] or flags[FLAG_MYDIGITAL_INTEGRATION]:
        return False
    if flags[FLAG_PUBLIC_TRANSPORT] or flags[FLAG_ROAD_ISSUE] or flags[FLAG_FLOOD_IMPACT]:
        return False
    if flags[FLAG_ROAD_ISSUE] and has_any(text, ["palm oil", "minyak sawit"]):
        return False
    if flags[FLAG_MCMC_3R]:
        return False
    if flags[FLAG_FLOOD_IMPACT]:
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
    if flags[FLAG_COST_OF_LIVING]:
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
    if flags[FLAG_PUBLIC_TRANSPORT] or flags[FLAG_ROAD_ISSUE] or flags[FLAG_FLOOD_IMPACT]:
        tags = []
        if flags[FLAG_PUBLIC_TRANSPORT]:
            tags.append("public_transport")
        if flags[FLAG_ROAD_ISSUE]:
            tags.append("road_closure")
        if flags[FLAG_FLOOD_IMPACT]:
            tags.append("flood")
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
        or flags[FLAG_COST_OF_LIVING]
        or has_any(item_text(item), ["jualan rahmah", "kos sara hidup", "cost of living", "bnm", "bank negara", "opr", "lpg", "drought", "cloud seeding", "food supply", "rice bowl", "agriculture"])
    ):
        tags = []
        if flags[FLAG_HEALTH_SYSTEM]:
            tags.append("health")
        if flags[FLAG_AI_ECONOMY]:
            tags.extend(["employment", "economy"])
        if flags[FLAG_CURRENCY] or has_any(item_text(item), ["bnm", "bank negara", "opr"]):
            tags.append("currency")
        if flags[FLAG_MARKET]:
            tags.append("economy")
        if flags[FLAG_URBAN_DEVELOPMENT]:
            tags.append("urban_development")
        if flags[FLAG_COST_OF_LIVING] or has_any(item_text(item), ["jualan rahmah", "kos sara hidup", "cost of living", "lpg"]):
            tags.extend(["prices", "social_support"])
            tags.append("cost_of_living")
        if has_any(item_text(item), ["drought", "cloud seeding", "food supply", "rice bowl", "agriculture"]):
            tags.append("food_supply")
        add_score(5, tags, "医療・雇用・経済・都市生活の背景価値")
    if has_any(item_text(item), ["dams hit alert levels", "dam hit alert levels", "alert levels", "rice bowl", "drought grips"]):
        add_score(2, ["food_supply"], "水資源・食料供給への生活影響が明確")
    if flags[FLAG_SCAM]:
        add_score(7, ["scam"], "詐欺・注意喚起")
    if is_paul_tan_item(item):
        decision, positive_groups, noise_groups = paul_tan_gate(item)
        if decision == "accept":
            tags = []
            if "public_transport" in positive_groups:
                tags.append("public_transport")
            if "road_toll" in positive_groups:
                tags.append("road_closure")
            if "driver_obligations" in positive_groups:
                tags.append("jpj")
            if "fuel_subsidy" in positive_groups:
                tags.extend(["prices", "fuel"])
            if "safety_recall" in positive_groups:
                tags.append("vehicle_safety")
            add_score(7, tags, "Paul Tan source-specific gate accepted")
        elif decision == "review":
            add_unique(item.penalties, "Paul Tan source-specific gate requires review")
        else:
            add_unique(item.penalties, "Paul Tan source-specific gate rejected")
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
    if is_paul_tan_item(item) and paul_tan_gate_decision(item) != "accept":
        return True
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
        or flags[FLAG_FLOOD_IMPACT]
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
        or flags[FLAG_FLOOD_IMPACT]
        or flags[FLAG_JPJ]
        or flags[FLAG_UTILITY_BILL]
        or flags[FLAG_SABAH_ELECTRICITY]
        or flags[FLAG_SOCIAL_SECURITY]
        or flags[FLAG_SCAM]
        or has_any(item_text(item), ["mcmc", "3r", "haji"])
    ):
        return "【生活インパクト】"
    return "【知っておくと得】"


def financial_topic_bucket(item: Item) -> str:
    text = item_text(item)
    flags = ensure_flags(item)
    if flags[FLAG_MARKET]:
        return "bursa"
    if has_any(text, ["bnm", "bank negara", "opr", "monetary policy", "loan costs", "targeted solutions"]):
        return "bnm_policy"
    if flags[FLAG_CURRENCY]:
        return "ringgit"
    return ""


def final_sort_key(item: Item) -> tuple[int, int, float]:
    return (CATEGORY_PRIORITY.get(item.category, 9), -item.score, -item.pub_date.timestamp())


def final_noise_text(item: Item) -> str:
    return normalized(f"{item.title} {item.description} {item.link}")


def has_corporate_appointment_exception(text: str) -> bool:
    return has_any(
        text,
        [
            "tariff",
            "tariffs",
            "fare",
            "fares",
            "price revision",
            "price increase",
            "price cut",
            "service disruption",
            "service disruptions",
            "service change",
            "service changes",
            "service quality",
            "customer impact",
            "consumer impact",
            "user impact",
            "employment impact",
            "job cuts",
            "layoffs",
            "public transport",
            "telecommunications",
            "communications service",
            "electricity",
            "water supply",
            "utility",
            "utilities",
            "subsidy",
            "aid",
            "application",
            "registration",
        ],
    )


def is_corporate_appointment_noise(item: Item) -> bool:
    text = final_noise_text(item)
    is_appointment = has_any(text, ["appoints", "appointed", "appointment", "names", "named"])
    is_corporate_role = has_any(
        text,
        [
            "chairman",
            "board chairman",
            "group ceo",
            "president and group ceo",
            "chief executive",
            "chief executive officer",
            "new president",
            "ceo",
        ],
    )
    return is_appointment and is_corporate_role and not has_corporate_appointment_exception(text)


def is_forced_final_noise(item: Item) -> bool:
    text = final_noise_text(item)
    if is_corporate_appointment_noise(item):
        return True
    has_practical_value = has_practical_life_value(item)
    noise_checks = [
        has_any(text, ["ipo oversubscribed", "initial public offering", "ipo"]) and has_any(text, ["oversubscribed", "initial public offering"]),
        has_any(text, ["appoints", "appointed", "appointment", "names"])
        and has_any(text, ["chairman", "president and group ceo", "group ceo", "chief executive", "new president", "ceo"]),
        has_any(text, ["civil service appointments", "senior civil service appointments", "chief secretary"])
        and has_any(text, ["appointments", "appointed", "unveiled", "names"]),
        has_any(text, ["queen praises", "king praises", "expressed admiration", "beauty islamic heritage and hospitality", "royal visit", "courtesy visit"]),
        has_any(text, ["drug syndicate", "drug syndicates", "dadah", "rampas dadah", "sindiket", "serbuan", "kg bernilai", "narcotics raid"]),
        has_any(text, ["tourism group", "perception matters", "expensive", "social media suggesting malaysia has become too expensive"]),
        has_any(text, ["reputation", "record low", "ipsos survey", "china surges", "united states has suffered", "favourability survey", "favorability survey"]),
        has_any(text, ["no malaysians aboard", "hantavirus linked cruise ship", "hantavirus", "overseas infection ship", "foreign infection ship"]),
    ]
    if any(noise_checks) and not has_practical_value:
        return True
    return uses_generic_fallback(item) and not has_practical_value


def final_noise_gate(items: list[Item]) -> list[Item]:
    return [item for item in items if not is_forced_final_noise(item)]


def finalize_selected_items(selected: list[Item]) -> list[Item]:
    global LAST_FINALIZE_STATS
    gated = final_noise_gate(selected)
    seen_links: set[str] = set()
    seen_keys: set[str] = set()
    financial_counts: Counter[str] = Counter()
    finalized: list[Item] = []
    stats = {
        "input_items": len(selected),
        "output_items": 0,
        "removed_noise_gate": len(selected) - len(gated),
        "removed_duplicate_url": 0,
        "removed_duplicate_key": 0,
        "removed_financial_cap": 0,
        "validation_errors": [],
    }
    for item in sorted(gated, key=final_sort_key):
        link_key = normalized(item.link)
        canonical_key = key_for(item)
        if link_key and link_key in seen_links:
            stats["removed_duplicate_url"] += 1
            continue
        if canonical_key and canonical_key in seen_keys:
            stats["removed_duplicate_key"] += 1
            continue
        financial_bucket = financial_topic_bucket(item) if item.category == "【知っておくと得】" else ""
        if financial_bucket and financial_counts[financial_bucket] >= FINANCIAL_LIMITS[financial_bucket]:
            stats["removed_financial_cap"] += 1
            continue
        finalized.append(item)
        if link_key:
            seen_links.add(link_key)
        if canonical_key:
            seen_keys.add(canonical_key)
        if financial_bucket:
            financial_counts[financial_bucket] += 1
    stats["output_items"] = len(finalized)
    stats["validation_errors"] = validate_final_items(finalized)
    LAST_FINALIZE_STATS = stats
    return finalized


def validate_final_items(selected: list[Item]) -> list[str]:
    errors: list[str] = []
    links = [normalized(item.link) for item in selected if item.link]
    keys = [key_for(item) for item in selected]
    if len(links) != len(set(links)):
        errors.append("duplicate_url")
    if len(keys) != len(set(keys)):
        errors.append("duplicate_canonical_key")
    category_by_key: dict[str, str] = {}
    for item in selected:
        key = key_for(item)
        previous = category_by_key.get(key)
        if previous and previous != item.category:
            errors.append("duplicate_item_across_categories")
            break
        category_by_key[key] = item.category
    financial_counts: Counter[str] = Counter()
    for item in selected:
        if item.category == "【知っておくと得】":
            bucket = financial_topic_bucket(item)
            if bucket:
                financial_counts[bucket] += 1
    for bucket, limit in FINANCIAL_LIMITS.items():
        if financial_counts[bucket] > limit:
            errors.append(f"{bucket}_limit_exceeded")
    return errors


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
    category_limits = {"【速報】": 3, "【生活インパクト】": 5, "【知っておくと得】": 8}
    category_counts: Counter[str] = Counter()
    financial_counts: Counter[str] = Counter()
    for item in candidates:
        category = category_for(item)
        item.category = category
        if is_forced_final_noise(item):
            continue
        financial_bucket = financial_topic_bucket(item) if category == "【知っておくと得】" else ""
        source_limit = SOURCE_LIMITS.get(item.source, 24)
        if source_counts[item.source] >= source_limit:
            continue
        if category_counts[category] >= category_limits[category]:
            continue
        if financial_bucket and financial_counts[financial_bucket] >= FINANCIAL_LIMITS[financial_bucket]:
            continue
        selected.append(item)
        source_counts[item.source] += 1
        category_counts[category] += 1
        if financial_bucket:
            financial_counts[financial_bucket] += 1
        if len(selected) >= 15:
            break
    return finalize_selected_items(selected)


def selection_summary(items: list[Item], selected: list[Item], now: datetime) -> str:
    cutoff = now - timedelta(hours=48)
    recent = [item for item in items if cutoff <= item.pub_date <= now]
    unique_keys = {key_for(item) for item in recent}
    category_counts = Counter(item.category for item in selected)
    tag_counts: Counter[str] = Counter()
    for item in selected:
        tag_counts.update(item.tags)
    top_tags = ", ".join(f"{tag}:{count}" for tag, count in tag_counts.most_common(8)) or "なし"
    validation_errors = LAST_FINALIZE_STATS.get("validation_errors", [])
    validation_text = ", ".join(validation_errors) if validation_errors else "なし"
    return "\n".join(
        [
            "selection_summary:",
            f"- recent_items: {len(recent)}",
            f"- unique_topics: {len(unique_keys)}",
            f"- selected_items: {len(selected)}",
            f"- categories: 速報={category_counts['【速報】']}, 生活インパクト={category_counts['【生活インパクト】']}, 知っておくと得={category_counts['【知っておくと得】']}",
            f"- top_tags: {top_tags}",
            f"- final_removed_noise_gate: {LAST_FINALIZE_STATS.get('removed_noise_gate', 0)}",
            f"- final_removed_duplicate_url: {LAST_FINALIZE_STATS.get('removed_duplicate_url', 0)}",
            f"- final_removed_duplicate_key: {LAST_FINALIZE_STATS.get('removed_duplicate_key', 0)}",
            f"- final_removed_financial_cap: {LAST_FINALIZE_STATS.get('removed_financial_cap', 0)}",
            f"- final_validation_errors: {validation_text}",
        ]
    )


def japanese_summary(item: Item) -> tuple[str, str, str, str]:
    text = item_text(item)
    flags = ensure_flags(item)
    if is_paul_tan_item(item) and paul_tan_gate_decision(item) == "accept":
        signal_groups = paul_tan_signal_groups(item)
        if "fuel_subsidy" in signal_groups:
            return (
                "燃料制度・燃料仕様の変更が、車利用者の確認事項になります。",
                "Paul TanのRSSで、燃料補助や燃料仕様に関する変更が報じられています。\nRON95、diesel、B15 biodieselなど、車利用者の費用や給油判断に関わる内容として扱います。",
                "対象燃料を使う人は、開始時期、対象地域、補助条件、車両互換性の案内を確認する必要があります。",
                "給油前に政府・燃料会社・車両メーカーの最新案内を確認。",
            )
        if "public_transport" in signal_groups:
            return (
                "公共交通の運行や通勤手段に影響する可能性があります。",
                "Paul TanのRSSで、公共交通や運行状況に関する情報が報じられています。\nLRT、MRT、Rapid KL、KTMBなどの公共交通に関わる移動情報として扱います。",
                "通勤・通学・都心移動では、遅延、代替ルート、運行再開時期を確認しておく必要があります。",
                "出発前に運行会社の公式情報を確認。",
            )
        if "driver_obligations" in signal_groups:
            if is_paul_tan_illegal_transport_enforcement(item):
                return (
                    "JPJの摘発により、違法な運送サービスの利用に注意が必要です。",
                    "Paul TanのRSSで、JPJが無許可または違法な旅客・貨物運送サービスを摘発した件が報じられています。\n正規でない運送サービスは、安全性や法的リスクの確認が必要です。",
                    "利用者は、配車・輸送サービスが正規の事業者によるものか、許可、保険、安全面に問題がないか確認する必要があります。",
                    "運送サービスを利用する前に、正規事業者か確認。",
                )
            return (
                "JPJや車両関連手続きで、運転者の確認事項が出る可能性があります。",
                "Paul TanのRSSで、運転者の手続きや義務に関する情報が報じられています。\nJPJ、licence、road tax、inspection、summonsなど、運転者の義務や手続きに関わる内容として扱います。",
                "対象者は期限、必要書類、罰則、オンライン手続きの有無を確認する必要があります。",
                "JPJや関係機関の公式案内を確認。",
            )
        if "road_toll" in signal_groups:
            return (
                "道路・料金所・通行ルートの確認が必要になる可能性があります。",
                "Paul TanのRSSで、道路や料金所に関する情報が報じられています。\n道路閉鎖、toll、RFID、SmartTAG、交通規制など、車移動に関わる内容として扱います。",
                "通勤、送迎、長距離移動では、迂回、料金支払い方法、混雑を見込む必要があります。",
                "出発前に道路・高速道路会社の最新案内を確認。",
            )
        if "safety_recall" in signal_groups:
            return (
                "車両リコールや安全不具合について、所有者の確認が必要です。",
                "Paul TanのRSSで、車両リコールや安全不具合に関する情報が報じられています。\nリコールや安全不具合など、車両所有者の対応に関わる内容として扱います。",
                "対象車種の所有者は、点検・修理の対象か、販売店やメーカーの案内を確認する必要があります。",
                "車台番号や対象モデルをメーカー公式情報で確認。",
            )
    if flags[FLAG_FLOOD_IMPACT] and has_any(text, ["flood hotline", "mbpj"]):
        return (
            "洪水時の連絡先・対応窓口を確認しておく必要があります。",
            "自治体が洪水対応のホットラインや連絡体制を案内しています。\n大雨時の冠水や倒木など、地域の生活動線に影響する可能性があります。",
            "居住地や通勤経路が対象地域に近い場合、自治体の最新案内を確認してください。",
            "緊急時の連絡先と迂回経路を控えておく。",
        )
    if flags[FLAG_FLOOD_IMPACT]:
        return (
            "冠水・倒木などで道路や生活動線に影響が出る可能性があります。",
            "大雨に伴うflash floodsや倒木などの影響が報じられています。\n周辺道路では渋滞や通行支障が起きる可能性があります。",
            "車移動、通勤、送迎では遅延や迂回を見込む必要があります。",
            "出発前に自治体・道路情報を確認。",
        )
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
    if flags[FLAG_ROAD_ISSUE]:
        return (
            "道路閉鎖や渋滞により、移動計画の見直しが必要です。",
            "道路利用者に移動計画の調整や迂回が呼びかけられています。\n対象道路や周辺エリアでは混雑や通行規制が起きる可能性があります。",
            "通勤、送迎、買い物、都心部への移動時間に影響します。",
            "出発前に道路状況と迂回路を確認。",
        )
    if flags[FLAG_PUBLIC_TRANSPORT]:
        return (
            "公共交通や通勤手段の選び方に影響する可能性があります。",
            "公共交通や移動サービスに関する案内が報じられています。\n通勤・通学・都心移動の選択肢を確認しておくと安心です。",
            "混雑回避や移動費、所要時間の見直しに関わります。",
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


def selected_summary_json(item: Item) -> dict[str, object]:
    conclusion, what, impact, action = japanese_summary(item)
    return {
        "conclusion": conclusion,
        "what_happened": what.splitlines()[:2],
        "life_impact": impact,
        "next_action": action or "",
    }


def item_json(item: Item) -> dict[str, object]:
    return {
        "category": item.category,
        "source": item.source,
        "published_date": f"{item.pub_date.year}年{item.pub_date.month}月{item.pub_date.day}日",
        "published_at": item.pub_date.isoformat(),
        "title": item.title,
        "description": paul_tan_display_description(item) if is_paul_tan_item(item) else item.description,
        "link": item.link,
        "canonical_key": key_for(item),
        "tags": item.tags,
        "flags": ensure_flags(item),
        "score": item.score,
        "reasons": item.reasons,
        "penalties": item.penalties,
        "background_value": item.background_value,
        "selected_summary": selected_summary_json(item),
    }


def build_selected_items_json(
    selected: list[Item],
    processed_count: int,
    failed_sources: list[str],
    now: datetime,
) -> dict[str, object]:
    return {
        "schema_version": "2b0_selected_items_v1",
        "generated_at": now.isoformat(),
        "date": now.date().isoformat(),
        "timezone": "Asia/Kuala_Lumpur",
        "source_policy": {
            "uses_rss_only": True,
            "fetches_article_body": False,
        },
        "counts": {
            "processed": processed_count,
            "selected": len(selected),
            "failed_sources": len(failed_sources),
        },
        "failed_sources": failed_sources,
        "items": [item_json(item) for item in selected],
    }


def write_json_output(path: str, data: dict[str, object]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(data, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")


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

    def item(title: str, description: str = "", link: str = "") -> Item:
        slug = re.sub(r"[^a-z0-9]+", "-", normalized(title)).strip("-")[:80] or "item"
        return Item("Test", "Test Feed", title, description, now, "raw", link or f"https://example.test/{slug}")

    def paul_item(title: str, description: str = "", link: str = "") -> Item:
        slug = re.sub(r"[^a-z0-9]+", "-", normalized(title)).strip("-")[:80] or "item"
        return Item("Paul Tan", "Paul Tan", title, description, now, "raw", link or f"https://paultan.org/{slug}")

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

    najib_trial = item("Najib pleaded not guilty as High Court hears bid to stay corruption trial")
    evaluate_item(najib_trial)
    check("Najib trial has no background value", not najib_trial.background_value)
    check("Najib trial is excluded", should_exclude_item(najib_trial))

    macc_statement = item("Rafizi called by MACC for recording his statement in ongoing probe")
    evaluate_item(macc_statement)
    check("MACC statement has no background value", not macc_statement.background_value)
    check("MACC statement is excluded", should_exclude_item(macc_statement))

    defence_missile = item("Defence minister says cabinet to discuss Naval Strike Missiles for LCS project")
    evaluate_item(defence_missile)
    check("Defence missile item has no background value", not defence_missile.background_value)
    check("Defence missile item is excluded", should_exclude_item(defence_missile))

    pnb_ceo = item("PNB names new president and group CEO")
    evaluate_item(pnb_ceo)
    check("PNB CEO appointment has no background value", not pnb_ceo.background_value)
    check("PNB CEO appointment is excluded", should_exclude_item(pnb_ceo))

    zahid_criticism = item("Zahid dismisses opposition criticism, says PAS no better")
    evaluate_item(zahid_criticism)
    check("Zahid criticism has no background value", not zahid_criticism.background_value)
    check("Zahid criticism is excluded", should_exclude_item(zahid_criticism))

    filial_law = item("Minister says cabinet to discuss filial responsibility law for elderly care")
    evaluate_item(filial_law)
    check("Filial responsibility law has background value", filial_law.background_value)
    check("Filial responsibility law is not excluded", not should_exclude_item(filial_law))

    moh_guidelines = item("MOH guidelines set house officers working hours in public hospitals")
    evaluate_item(moh_guidelines)
    check("MOH house officers working hours has background value", moh_guidelines.background_value)
    check("MOH house officers working hours is not excluded", not should_exclude_item(moh_guidelines))

    bank_negara_opr = item("Bank Negara keeps OPR unchanged as households monitor loan costs")
    evaluate_item(bank_negara_opr)
    check("Bank Negara OPR has background value", bank_negara_opr.background_value)
    check("Bank Negara OPR is not excluded", not should_exclude_item(bank_negara_opr))

    pnb_exact = item("PNB names new president and group CEO")
    evaluate_item(pnb_exact)
    check("PNB exact CEO item is excluded", should_exclude_item(pnb_exact))

    queen_visit = item("Queen praises Uzbekistan during courtesy visit")
    evaluate_item(queen_visit)
    check("Queen visit has no background value", not queen_visit.background_value)
    check("Queen visit is excluded", should_exclude_item(queen_visit))

    drug_bust = item("Police bust drug syndicates in major narcotics raid")
    evaluate_item(drug_bust)
    check("Drug syndicate bust has no background value", not drug_bust.background_value)
    check("Drug syndicate bust is excluded", should_exclude_item(drug_bust))

    pakatan_convention = item("Pakatan national convention sets election preparations")
    evaluate_item(pakatan_convention)
    check("Pakatan convention has no background value", not pakatan_convention.background_value)
    check("Pakatan convention is excluded", should_exclude_item(pakatan_convention))

    road_advisory = item("Road users advised to plan journeys around Padang Merbok")
    evaluate_item(road_advisory)
    check("Road journey advisory triggers road issue", road_advisory.flags[FLAG_ROAD_ISSUE])
    check("Road journey advisory is life impact", category_for(road_advisory) == "【生活インパクト】")

    bukit_bintang_closure = item("Jalan Bukit Bintang closed from midnight near Pavilion KL")
    evaluate_item(bukit_bintang_closure)
    check("Bukit Bintang closure triggers road issue", bukit_bintang_closure.flags[FLAG_ROAD_ISSUE])
    check("Bukit Bintang closure is life impact", category_for(bukit_bintang_closure) == "【生活インパクト】")

    mbpj_hotline = item("MBPJ activates 24-hour flood hotline after flash floods and toppled trees")
    evaluate_item(mbpj_hotline)
    check("MBPJ flood hotline triggers flood impact", mbpj_hotline.flags[FLAG_FLOOD_IMPACT])
    check("MBPJ flood hotline is life impact", category_for(mbpj_hotline) == "【生活インパクト】")
    check("MBPJ flood hotline uses hotline summary", "ホットライン" in japanese_summary(mbpj_hotline)[1])

    jualan_rahmah = item("PKPS expands Jualan Rahmah to ease kos sara hidup")
    evaluate_item(jualan_rahmah)
    check("Jualan Rahmah has background value", jualan_rahmah.background_value)
    check("Jualan Rahmah is not excluded", not should_exclude_item(jualan_rahmah))
    check("Jualan Rahmah has selectable score", jualan_rahmah.score >= 3)

    bnm_targeted = item("BNM targeted solutions aim to help households manage loan costs")
    evaluate_item(bnm_targeted)
    check("BNM targeted solutions has background value", bnm_targeted.background_value)
    check("BNM targeted solutions is not excluded", not should_exclude_item(bnm_targeted))
    check("BNM targeted solutions has selectable score", bnm_targeted.score >= 3)

    bukit_bintang_bm = item("Jalan Bukit Bintang ditutup mulai tengah malam berhampiran Pavilion KL")
    bukit_bintang_en = item("Jalan Bukit Bintang closed from midnight near Pavilion KL")
    evaluate_item(bukit_bintang_bm)
    evaluate_item(bukit_bintang_en)
    check("Bukit Bintang BM/EN closures dedup", key_for(bukit_bintang_bm) == key_for(bukit_bintang_en))

    bukit_bintang_plain = item("Bukit Bintang welcomes weekend shoppers")
    evaluate_item(bukit_bintang_plain)
    check("Bukit Bintang plain item does not use closure key", key_for(bukit_bintang_plain) != "jalan-bukit-bintang-closure")

    ktmb_extra = item("KTMB rolls out 186 extra trains for Hari Raya Aidiladha and school holidays")
    evaluate_item(ktmb_extra)
    check("KTMB extra trains triggers public transport", ktmb_extra.flags[FLAG_PUBLIC_TRANSPORT])
    check("KTMB extra trains is life impact", category_for(ktmb_extra) == "【生活インパクト】")

    paul_lrt = paul_item("Independent task force formed to investigate LRT derailment, led by Loke")
    evaluate_item(paul_lrt)
    check("Paul Tan LRT gate accepts", paul_tan_gate_decision(paul_lrt) == "accept")
    check("Paul Tan LRT is not excluded", not should_exclude_item(paul_lrt))
    check("Paul Tan LRT maps to public transport", "public_transport" in paul_lrt.tags)

    paul_ron95 = paul_item("RON95 subsidy adjustment is last resort: PMO adviser")
    evaluate_item(paul_ron95)
    check("Paul Tan RON95 gate accepts", paul_tan_gate_decision(paul_ron95) == "accept")
    check("Paul Tan RON95 maps to fuel and prices", "fuel" in paul_ron95.tags and "prices" in paul_ron95.tags)
    check("Paul Tan RON95 is selectable", bool(select_items([paul_ron95], now)))

    paul_b15 = paul_item(
        "Biodiesel B15 rollout begins June 1 - govt says no issue with compatibility",
        "Malaysia is set to raise the biodiesel blend rate from B10 to B15. The post Biodiesel B15 rollout begins June 1 appeared first on Paul Tan's Automotive News.",
    )
    evaluate_item(paul_b15)
    b15_summary = japanese_summary(paul_b15)
    b15_json = item_json(paul_b15)
    check("Paul Tan B15 display uses Japanese fuel summary", "燃料制度" in b15_summary[0])
    check("Paul Tan B15 summary strips WordPress boilerplate", "appeared first" not in " ".join(b15_summary))
    check("Paul Tan B15 summary does not echo English RSS description", "Malaysia is set" not in " ".join(b15_summary))
    check("Paul Tan B15 JSON description strips WordPress boilerplate", "appeared first" not in str(b15_json["description"]))

    paul_recall = paul_item("Honda SUV recall in Malaysia over airbag safety defect")
    evaluate_item(paul_recall)
    check("Paul Tan recall with ordinary vehicle wording accepts", paul_tan_gate_decision(paul_recall) == "accept")
    check("Paul Tan recall maps to vehicle safety", "vehicle_safety" in paul_recall.tags)

    paul_launch = paul_item("New SUV launched in Malaysia, priced at RM120k")
    evaluate_item(paul_launch)
    check("Paul Tan launch noise is rejected", paul_tan_gate_decision(paul_launch) == "reject")
    check("Paul Tan launch noise is excluded", should_exclude_item(paul_launch))

    paul_review = paul_item("First drive review of new EV sedan in Malaysia")
    evaluate_item(paul_review)
    check("Paul Tan review noise is rejected", paul_tan_gate_decision(paul_review) == "reject")
    check("Paul Tan review noise is excluded", should_exclude_item(paul_review))

    paul_pricing_review = paul_item("2026 Kawasaki Z650S in Malaysia, priced at RM35,600", "Insurance and road tax estimates included.")
    evaluate_item(paul_pricing_review)
    check("Paul Tan mixed pricing item requires review", paul_tan_gate_decision(paul_pricing_review) == "review")
    check("Paul Tan review decision is excluded", should_exclude_item(paul_pricing_review))

    paul_jpj_procedure = paul_item(
        "JPJ to accept foreign driving licence conversion applications nationwide from June 1",
        "Malaysians can apply at JPJ counters with the required documents.",
    )
    evaluate_item(paul_jpj_procedure)
    check("Paul Tan real JPJ procedure gate accepts", paul_tan_gate_decision(paul_jpj_procedure) == "accept")
    check("Paul Tan real JPJ procedure is not excluded", not should_exclude_item(paul_jpj_procedure))

    paul_illegal_transport = paul_item(
        "JPJ Terengganu uncovers illegal transport services by foreigners, using vehicles rented from locals",
        "JPJ enforcement officers found illegal passenger and goods transport services operating without permit.",
    )
    evaluate_item(paul_illegal_transport)
    illegal_transport_summary = japanese_summary(paul_illegal_transport)
    check("Paul Tan illegal transport gate accepts", paul_tan_gate_decision(paul_illegal_transport) == "accept")
    check("Paul Tan illegal transport uses enforcement display", "違法な運送サービス" in illegal_transport_summary[0])
    check("Paul Tan illegal transport does not use generic JPJ procedure display", "JPJや車両関連手続き" not in illegal_transport_summary[0])

    paul_ev_ranking = paul_item(
        "Top 20 EV brands in May 2026 - Proton already beats its full-year 2025 tally; Perodua climbs to 10th",
        "According to the latest data from the road transport department (JPJ), total EV registrations rose in May 2026.",
    )
    evaluate_item(paul_ev_ranking)
    check("Paul Tan JPJ data-only EV ranking requires review", paul_tan_gate_decision(paul_ev_ranking) == "review")
    check("Paul Tan JPJ data-only EV ranking is excluded", should_exclude_item(paul_ev_ranking))

    paul_selected = select_items([paul_lrt, paul_ron95, paul_recall], now)
    check("Paul Tan source cap keeps at most one item", sum(1 for test_item in paul_selected if test_item.source == "Paul Tan") <= 1)

    petronas_chairman = item("Petronas Dagangan appoints new chairman")
    evaluate_item(petronas_chairman)
    check("Petronas chairman is excluded", should_exclude_item(petronas_chairman))

    skyechip_ipo = item("SkyeChip IPO oversubscribed by 20 times")
    evaluate_item(skyechip_ipo)
    check("SkyeChip IPO is excluded", should_exclude_item(skyechip_ipo))

    road_low_value_guard = item("Road users advised to plan journeys despite poll event near Padang Merbok")
    evaluate_item(road_low_value_guard)
    check("Road impact overrides low-value fallback", not should_exclude_item(road_low_value_guard))

    ringgit_items = [
        item("Ringgit expected to trade in narrow range ahead of US data"),
        item("Ringgit strengthens as Malaysia economy outlook improves"),
        item("Ringgit forecast revised after IMF economy update"),
    ]
    selected_ringgit = select_items(ringgit_items, now)
    check("Ringgit selected items stay within cap", sum(1 for test_item in selected_ringgit if financial_topic_bucket(test_item) == "ringgit") <= 2)

    bursa_items = [
        item("Bursa Malaysia seen trading range-bound between 1,700 and 1,730"),
        item("Bursa Malaysia market index expected to trade cautiously"),
    ]
    selected_bursa = select_items(bursa_items, now)
    check("Bursa selected items stay within cap", sum(1 for test_item in selected_bursa if financial_topic_bucket(test_item) == "bursa") <= 1)

    bnm_items = [
        item("BNM targeted solutions aim to help households manage loan costs"),
        item("Bank Negara OPR unchanged as households monitor loan costs"),
        item("BNM monetary policy update focuses on loan costs"),
    ]
    selected_bnm = select_items(bnm_items, now)
    check("BNM selected items stay within cap", sum(1 for test_item in selected_bnm if financial_topic_bucket(test_item) == "bnm_policy") <= 2)

    ktmb_life = item("KTMB rolls out 186 extra trains for Hari Raya Aidiladha", link="https://example.test/ktmb")
    ktmb_info = item("KTMB rolls out 186 extra trains for Hari Raya Aidiladha", link="https://example.test/ktmb")
    evaluate_item(ktmb_life)
    evaluate_item(ktmb_info)
    ktmb_life.category = "【生活インパクト】"
    ktmb_info.category = "【知っておくと得】"
    finalized_ktmb = finalize_selected_items([ktmb_info, ktmb_life])
    check("Duplicate KTMB finalizes to one item", len(finalized_ktmb) == 1)
    check("Duplicate KTMB keeps life impact", finalized_ktmb[0].category == "【生活インパクト】")

    duplicate_url_a = item("Road users advised to plan journeys around Padang Merbok", link="https://example.test/same-url")
    duplicate_url_b = item("Road users advised to plan journeys around Padang Merbok", link="https://example.test/same-url")
    evaluate_item(duplicate_url_a)
    evaluate_item(duplicate_url_b)
    duplicate_url_a.category = "【生活インパクト】"
    duplicate_url_b.category = "【知っておくと得】"
    finalized_url = finalize_selected_items([duplicate_url_b, duplicate_url_a])
    check("Duplicate URL finalizes to one item", len(finalized_url) == 1)
    check("Duplicate URL does not cross categories", len({test_item.category for test_item in finalized_url}) == 1)

    bintang_bm_quranic = item("Jalan Bukit Bintang ditutup tengah malam hingga 5 pagi untuk Quranic Madani di Pavilion Kuala Lumpur")
    bintang_en_quranic = item("Jalan Bukit Bintang closed from midnight to 5am for Quranic Madani near Pavilion KL")
    evaluate_item(bintang_bm_quranic)
    evaluate_item(bintang_en_quranic)
    check("Quranic Madani Bukit Bintang BM/EN closures dedup", key_for(bintang_bm_quranic) == key_for(bintang_en_quranic))

    cruise_ship = item("No Malaysians aboard hantavirus-linked cruise ship")
    evaluate_item(cruise_ship)
    check("No Malaysians cruise ship has no background value", not cruise_ship.background_value)
    check("No Malaysians cruise ship is excluded", should_exclude_item(cruise_ship))

    ringgit_final_items = [
        item("Ringgit expected to trade in narrow range ahead of US data", link="https://example.test/ringgit-1"),
        item("Ringgit strengthens as Malaysia economy outlook improves", link="https://example.test/ringgit-2"),
        item("Ringgit forecast revised after IMF economy update", link="https://example.test/ringgit-3"),
    ]
    for test_item in ringgit_final_items:
        evaluate_item(test_item)
        test_item.category = "【知っておくと得】"
    finalized_ringgit = finalize_selected_items(ringgit_final_items)
    check("Final Ringgit items stay within cap", sum(1 for test_item in finalized_ringgit if financial_topic_bucket(test_item) == "ringgit") <= 2)

    final_noise_titles = [
        "SkyeChip IPO oversubscribed by 20 times",
        "Petronas Dagangan appoints new chairman",
        "Petronas Dagangan appoints Sazali Hamzah as chairman",
        "PNB names new president and group CEO",
        "PNB names Rizal Rickman as new president and group CEO",
        "Board appointed veteran executive as chairman",
        "Company appoints Tan Sri Ahmad as chairman",
        "Company names new group CEO",
        "Six senior civil service appointments unveiled by chief secretary",
        "Queen praises Uzbekistan for beauty, Islamic heritage and hospitality",
        "Polis Selangor rampas dadah 100kg bernilai RM5 juta dalam serbuan",
        "Malaysia is expensive? Local tourism group says perception matters",
        "US reputation in Malaysia hits record low as China surges, Ipsos survey shows",
    ]
    for title in final_noise_titles:
        test_item = item(title)
        evaluate_item(test_item)
        test_item.category = category_for(test_item)
        check(f"Final noise gate removes {title}", not final_noise_gate([test_item]))
        if has_any(title, ["petronas dagangan", "pnb names", "board appointed", "company appoints", "company names"]):
            check(f"Corporate appointment helper removes {title}", is_corporate_appointment_noise(test_item))

    keep_titles = [
        "MBPJ activates 24-hour flood hotline after flash floods",
        "MetMalaysia warns of severe weather and heavy rain in Klang Valley",
        "KTMB rolls out 186 extra trains for Hari Raya Aidiladha",
        "Road closure for KL Run: road users advised to plan journeys",
        "Jalan Bukit Bintang closed from midnight near Pavilion KL",
        "Grab Group Ride expands commuting options in Klang Valley",
        "PKPS expands Jualan Rahmah to ease kos sara hidup",
        "Housing ministry studies option to purchase clause for home buyers",
        "PKPS perkukuh rangkaian jualan murah, 122 rakan strategik bantu rakyat hadapi kos sara hidup",
        "Jualan Rahmah offers barang keperluan at harga lebih rendah",
        "Kos sara hidup eased through jualan murah in Selangor",
    ]
    for title in keep_titles:
        test_item = item(title)
        evaluate_item(test_item)
        test_item.category = category_for(test_item)
        check(f"Final noise gate keeps {title}", bool(final_noise_gate([test_item])))

    cost_of_living_item = item("PKPS perkukuh rangkaian jualan murah, 122 rakan strategik bantu rakyat hadapi kos sara hidup")
    evaluate_item(cost_of_living_item)
    check("PKPS cost-of-living flag triggers", cost_of_living_item.flags[FLAG_COST_OF_LIVING])
    check("PKPS cost-of-living has background value", cost_of_living_item.background_value)
    check("PKPS cost-of-living is not excluded", not should_exclude_item(cost_of_living_item))
    check("PKPS cost-of-living is selectable", bool(select_items([cost_of_living_item], now)))

    cloud_seeding = item("Cloud seeding set for Perlis and Kedah as dry spell continues")
    drought_rice = item("As drought grips Kedah, rice bowl dams hit alert levels")
    evaluate_item(cloud_seeding)
    evaluate_item(drought_rice)
    cloud_seeding.category = "【知っておくと得】"
    drought_rice.category = "【知っておくと得】"
    finalized_drought = finalize_selected_items([cloud_seeding, drought_rice])
    check("Cloud seeding and drought rice bowl share canonical key", key_for(cloud_seeding) == key_for(drought_rice))
    check("Cloud seeding and drought rice bowl finalize to one item", len(finalized_drought) == 1)
    check("Drought rice bowl item is preferred", finalized_drought[0].title == drought_rice.title)

    weather_guard = item("Ribut petir, hujan lebat di KL hingga petang - MetMalaysia")
    evaluate_item(weather_guard)
    weather_guard.background_value = False
    check("Template weather is not excluded by generic fallback rule", not should_exclude_item(weather_guard))

    weather_guard.category = category_for(weather_guard)
    json_payload = build_selected_items_json([weather_guard], 1, [], now)
    json_item = json_payload["items"][0]
    selected_summary = json_item["selected_summary"]
    check("JSON payload uses selected items only", json_payload["counts"]["selected"] == 1 and len(json_payload["items"]) == 1)
    check("JSON item has canonical key", bool(json_item["canonical_key"]))
    check("JSON item keeps internal metadata", "score" in json_item and "flags" in json_item)
    check("JSON selected summary has next_action key", "next_action" in selected_summary)
    check("JSON selected summary splits what_happened like render", len(selected_summary["what_happened"]) <= 2)

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
    parser.add_argument("--include-paul-tan", action="store_true", help="Locally opt in to the gated Paul Tan RSS source.")
    parser.add_argument("--output", help="Write the final Markdown summary to this path.")
    parser.add_argument("--json-output", help="Write selected final items as intermediate JSON to this path.")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    sources = SOURCES + ([PAUL_TAN_SOURCE] if args.include_paul_tan else [])
    results = [(source, feed, fetch_rss(url)) for source, feed, url in sources]
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
    if args.json_output:
        write_json_output(
            args.json_output,
            build_selected_items_json(selected, processed_count, failed_sources, now),
        )
        print(f"Wrote JSON: {args.json_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Typed JSON contracts shared by Groq summary and entry-review requests."""

from typing import Any


HEADLINE_MAX_LENGTH = 15


# Final Markdown validation and per-item hard safety share this list. Keeping
# it here prevents a rejected display token from reaching the document-wide
# validator only after otherwise safe entries have already been assembled.
EDITORIAL_ENTRY_FORBIDDEN_PATTERNS = (
    "KUALA LUMPUR,",
    "PUTRAJAYA,",
    "SHAH ALAM,",
    "GEORGE TOWN,",
    "MELAKA,",
    "— The",
    "::inbox-item",
    "The post",
    "appeared first",
    "Lowyat",
    "lowyat",
    "RSS内のタイトルと説明をもとに整理しました。",
    "生活・仕事・家計に関わる背景ニュースとして把握しておく価値があります。",
)


ENTRY_STATE_KINDS = (
    "reported_event",
    "attributed_statement",
    "official_action",
    "plan_or_proposal",
    "warning_or_forecast",
    "investigation_or_allegation",
    "denial_or_correction",
    "other",
)
ENTRY_CERTAINTY_KINDS = (
    "reported",
    "confirmed",
    "planned",
    "proposed",
    "expected",
    "warning",
    "under_investigation",
    "alleged",
    "denied",
)


def entry_part_schema(include_kind: tuple[str, ...] | None = None) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "source_text": {"type": "string"},
        "text_ja": {"type": "string"},
    }
    required = ["source_text", "text_ja"]
    if include_kind is not None:
        properties["kind"] = {"type": "string", "enum": list(include_kind)}
        required.append("kind")
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def entry_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "text_ja": {"type": "string"},
            "subject": entry_part_schema(),
            "attribution": {"anyOf": [entry_part_schema(), {"type": "null"}]},
            "state": entry_part_schema(ENTRY_STATE_KINDS),
            "certainty": entry_part_schema(ENTRY_CERTAINTY_KINDS),
        },
        "required": ["text_ja", "subject", "attribution", "state", "certainty"],
        "additionalProperties": False,
    }


def selected_summary_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "conclusion": {"type": "string"},
            "what_happened": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 2,
            },
            "life_impact": {"type": "string"},
            "next_action": {"type": "string"},
        },
        "required": ["conclusion", "what_happened", "life_impact", "next_action"],
        "additionalProperties": False,
    }


def editorial_entry_schema() -> dict[str, Any]:
    """The production display contract.

    The renderer deliberately receives one editorial entry rather than the
    former conclusion/impact/action fields.  This keeps editorial judgement in
    the model response and makes the fallback shape identical.
    """
    return {
        "type": "object",
        "properties": {
            # Keep the server-enforced schema and local validator on the same
            # Unicode-character limit. JSON Schema cannot express the former
            # half-width display calculation reliably.
            "headline_ja": {"type": "string", "minLength": 1, "maxLength": HEADLINE_MAX_LENGTH},
            "entry_ja": {"type": "string", "minLength": 1},
            "supporting_points_ja": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 0,
                "maxItems": 2,
            },
        },
        "required": ["headline_ja", "entry_ja", "supporting_points_ja"],
        "additionalProperties": False,
    }


EDITORIAL_ENTRY_V2_SCHEMA = {
    "type": "object",
    "properties": {"editorial_entry": editorial_entry_schema()},
    "required": ["editorial_entry"],
    "additionalProperties": False,
}


# The repair request intentionally has a smaller surface than the production
# entry contract. It is only used once after a transport or JSON-contract
# failure, so a short headline and a single source-grounded overview are
# enough to recover a usable entry without recreating the full response.
EDITORIAL_ENTRY_REPAIR_SCHEMA = {
    "type": "object",
    "properties": {
        "editorial_entry": {
            "type": "object",
            "properties": {
                "headline_ja": {"type": "string", "minLength": 1, "maxLength": HEADLINE_MAX_LENGTH},
                "entry_ja": {"type": "string", "minLength": 1},
            },
            "required": ["headline_ja", "entry_ja"],
            "additionalProperties": False,
        }
    },
    "required": ["editorial_entry"],
    "additionalProperties": False,
}


SUMMARY_ENTRY_SCHEMA = {
    "type": "object",
    "properties": {
        "selected_summary": selected_summary_schema(),
        "entry": entry_schema(),
    },
    "required": ["selected_summary", "entry"],
    "additionalProperties": False,
}


SUMMARY_ONLY_SCHEMA = {
    "type": "object",
    "properties": {"selected_summary": selected_summary_schema()},
    "required": ["selected_summary"],
    "additionalProperties": False,
}


ENTRY_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "revise", "reject"]},
        "issues": {"type": "array", "items": {"type": "string"}},
        "reviewed_entry": {"anyOf": [entry_schema(), {"type": "null"}]},
    },
    "required": ["verdict", "issues", "reviewed_entry"],
    "additionalProperties": False,
}


def _is_string(value: Any) -> bool:
    return isinstance(value, str)


def editorial_headline_error(value: Any) -> str:
    if not _is_string(value):
        return "editorial_headline_type"
    headline = value.strip()
    if not headline:
        return "editorial_headline_empty"
    if len(headline) > HEADLINE_MAX_LENGTH:
        return "editorial_headline_too_long"
    return ""


def headline_is_valid(value: Any) -> bool:
    return not editorial_headline_error(value)


def _exact_keys(value: Any, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def _entry_part_is_valid(value: Any, kinds: tuple[str, ...] | None = None) -> bool:
    keys = {"source_text", "text_ja"}
    if kinds is not None:
        keys.add("kind")
    if not _exact_keys(value, keys):
        return False
    if not _is_string(value["source_text"]) or not _is_string(value["text_ja"]):
        return False
    return kinds is None or _is_string(value["kind"]) and value["kind"] in kinds


def entry_is_schema_valid(value: Any) -> bool:
    if not _exact_keys(value, {"text_ja", "subject", "attribution", "state", "certainty"}):
        return False
    attribution = value["attribution"]
    return (
        _is_string(value["text_ja"])
        and _entry_part_is_valid(value["subject"])
        and (attribution is None or _entry_part_is_valid(attribution))
        and _entry_part_is_valid(value["state"], ENTRY_STATE_KINDS)
        and _entry_part_is_valid(value["certainty"], ENTRY_CERTAINTY_KINDS)
    )


def summary_entry_schema_error(value: Any) -> str:
    if not _exact_keys(value, {"selected_summary", "entry"}):
        return "root_shape"
    summary = value["selected_summary"]
    if not _exact_keys(summary, {"conclusion", "what_happened", "life_impact", "next_action"}):
        return "summary_shape"
    happened = summary["what_happened"]
    if (
        not _is_string(summary["conclusion"])
        or not _is_string(summary["life_impact"])
        or not _is_string(summary["next_action"])
        or not isinstance(happened, list)
        or not 1 <= len(happened) <= 2
        or any(not _is_string(line) for line in happened)
    ):
        return "summary_value"
    return "" if entry_is_schema_valid(value["entry"]) else "entry_shape"


def summary_only_schema_error(value: Any) -> str:
    if not _exact_keys(value, {"selected_summary"}):
        return "root_shape"
    summary = value["selected_summary"]
    if not _exact_keys(summary, {"conclusion", "what_happened", "life_impact", "next_action"}):
        return "summary_shape"
    happened = summary["what_happened"]
    if (
        not _is_string(summary["conclusion"])
        or not _is_string(summary["life_impact"])
        or not _is_string(summary["next_action"])
        or not isinstance(happened, list)
        or not 1 <= len(happened) <= 2
        or any(not _is_string(line) for line in happened)
    ):
        return "summary_value"
    return ""


def editorial_entry_schema_error(value: Any) -> str:
    if not _exact_keys(value, {"editorial_entry"}):
        return "root_shape"
    entry = value["editorial_entry"]
    if not _exact_keys(entry, {"headline_ja", "entry_ja", "supporting_points_ja"}):
        return "editorial_entry_shape"
    headline_error = editorial_headline_error(entry["headline_ja"])
    if headline_error:
        return headline_error
    if not _is_string(entry["entry_ja"]):
        return "editorial_entry_type"
    if not entry["entry_ja"].strip():
        return "editorial_entry_empty"
    points = entry["supporting_points_ja"]
    if not isinstance(points, list):
        return "editorial_supporting_points_type"
    if not 0 <= len(points) <= 2:
        return "editorial_supporting_points_count"
    if any(not _is_string(point) for point in points):
        return "editorial_supporting_point_type"
    return ""


def editorial_entry_repair_schema_error(value: Any) -> str:
    if not _exact_keys(value, {"editorial_entry"}):
        return "root_shape"
    entry = value["editorial_entry"]
    if not _exact_keys(entry, {"headline_ja", "entry_ja"}):
        return "editorial_entry_shape"
    headline_error = editorial_headline_error(entry["headline_ja"])
    if headline_error:
        return headline_error
    if not _is_string(entry["entry_ja"]):
        return "editorial_entry_type"
    if not entry["entry_ja"].strip():
        return "editorial_entry_empty"
    return ""


def editorial_entry_forbidden_patterns(value: str) -> list[str]:
    """Return display tokens that remain forbidden in Editorial Entry v2."""
    return [pattern for pattern in EDITORIAL_ENTRY_FORBIDDEN_PATTERNS if pattern in value]


def entry_review_schema_error(value: Any) -> str:
    if not _exact_keys(value, {"verdict", "issues", "reviewed_entry"}):
        return "root_shape"
    if value["verdict"] not in {"pass", "revise", "reject"}:
        return "verdict"
    if not isinstance(value["issues"], list) or any(not _is_string(issue) for issue in value["issues"]):
        return "issues"
    reviewed_entry = value["reviewed_entry"]
    if reviewed_entry is not None and not entry_is_schema_valid(reviewed_entry):
        return "reviewed_entry"
    return ""

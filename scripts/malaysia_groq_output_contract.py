"""Typed JSON contracts shared by Groq summary and entry-review requests."""

from typing import Any


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

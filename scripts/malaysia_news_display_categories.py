"""Shared public display categories for Malaysia News.

Legacy categories remain selection metadata. This module maps them, and Jev's
relevance decision when present, to the smaller set used in public Markdown.
"""

from __future__ import annotations

from typing import Any


LIVING_UPDATES = "【暮らしに関わる更新】"
SOCIETY_ECONOMY = "【社会・経済の動き】"
DISPLAY_CATEGORIES = (LIVING_UPDATES, SOCIETY_ECONOMY)

LEGACY_CATEGORY_MAP = {
    "【速報】": LIVING_UPDATES,
    "【生活インパクト】": LIVING_UPDATES,
    "【知っておくと得】": SOCIETY_ECONOMY,
}
LEGACY_CATEGORIES = tuple(LEGACY_CATEGORY_MAP)
MARKDOWN_CATEGORIES = (*DISPLAY_CATEGORIES, *LEGACY_CATEGORIES)


def display_category_for_legacy(category: Any) -> str:
    """Map historical selection labels without changing their selection role."""
    value = category.strip() if isinstance(category, str) else ""
    if value in DISPLAY_CATEGORIES:
        return value
    return LEGACY_CATEGORY_MAP.get(value, SOCIETY_ECONOMY)


def display_category_for_jev(decision: Any, legacy_category: Any = "") -> str:
    """Prefer the semantic decision only where it has an explicit meaning."""
    if decision == "direct_life_impact":
        return LIVING_UPDATES
    if decision == "public_information":
        return SOCIETY_ECONOMY
    return display_category_for_legacy(legacy_category)


def display_category_for_item(item: dict[str, Any]) -> str:
    explicit = item.get("display_category")
    if isinstance(explicit, str) and explicit in DISPLAY_CATEGORIES:
        return explicit
    return display_category_for_legacy(item.get("category"))

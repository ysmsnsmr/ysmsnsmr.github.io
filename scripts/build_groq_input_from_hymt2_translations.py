#!/usr/bin/env python3
import argparse
import copy
import json
from pathlib import Path
from typing import Any


ADAPTER_VERSION = "phase2c.3.v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply Hy-MT2 translated fields to selected_items JSON for Groq rendering experiments."
    )
    parser.add_argument("--source-json", required=True, help="Original selected_items.json path.")
    parser.add_argument("--translated-json", required=True, help="Hy-MT2 translated_items.json path.")
    parser.add_argument("--output", required=True, help="Output Groq-compatible selected_items JSON path.")
    return parser.parse_args()


def load_json(path: str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as input_file:
        data = json.load(input_file)
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def write_json(path: str, payload: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(payload, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")


def text_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def source_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = data.get("items", [])
    if not isinstance(raw_items, list):
        raise ValueError("source-json must contain an items array.")
    if not all(isinstance(item, dict) for item in raw_items):
        raise ValueError("source-json items must be objects.")
    return raw_items


def translated_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = data.get("items", [])
    if not isinstance(raw_items, list):
        raise ValueError("translated-json must contain an items array.")
    return [item for item in raw_items if isinstance(item, dict)]


def build_translation_indexes(items: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[int, dict[str, Any]]]:
    by_link: dict[str, dict[str, Any]] = {}
    by_index: dict[int, dict[str, Any]] = {}
    for item in items:
        link = text_value(item.get("link")).strip()
        if link and link not in by_link:
            by_link[link] = item
        index = item.get("index")
        if isinstance(index, int) and index not in by_index:
            by_index[index] = item
    return by_link, by_index


def matching_translation(
    source_item: dict[str, Any],
    position: int,
    by_link: dict[str, dict[str, Any]],
    by_index: dict[int, dict[str, Any]],
) -> dict[str, Any] | None:
    link = text_value(source_item.get("link")).strip()
    if link and link in by_link:
        return by_link[link]
    return by_index.get(position)


def apply_translation(source_item: dict[str, Any], translation: dict[str, Any] | None) -> tuple[dict[str, Any], int]:
    item = copy.deepcopy(source_item)
    item["source_title"] = source_item.get("title", "")
    item["source_description"] = source_item.get("description", "")

    applied_fields = 0
    if translation:
        translated_title = text_value(translation.get("translated_title")).strip()
        translated_description = text_value(translation.get("translated_description")).strip()
        if translated_title:
            item["title"] = translated_title
            applied_fields += 1
        if translated_description:
            item["description"] = translated_description
            applied_fields += 1

        item["hymt2_translation_status"] = translation.get("translation_status", "")
        item["hymt2_translation_field_status"] = copy.deepcopy(translation.get("translation_field_status", {}))
        item["hymt2_translation_elapsed_ms"] = translation.get("translation_elapsed_ms", 0)
    else:
        item["hymt2_translation_status"] = ""
        item["hymt2_translation_field_status"] = {}
        item["hymt2_translation_elapsed_ms"] = 0

    return item, applied_fields


def build_output(source_data: dict[str, Any], translated_data: dict[str, Any], translated_json_path: str) -> dict[str, Any]:
    output = copy.deepcopy(source_data)
    source = source_items(source_data)
    translated = translated_items(translated_data)
    by_link, by_index = build_translation_indexes(translated)

    output_items: list[dict[str, Any]] = []
    applied_items = 0
    applied_fields_total = 0

    for zero_index, source_item in enumerate(source):
        translation = matching_translation(source_item, zero_index + 1, by_link, by_index)
        output_item, applied_fields = apply_translation(source_item, translation)
        if applied_fields:
            applied_items += 1
            applied_fields_total += applied_fields
        output_items.append(output_item)

    output["items"] = output_items
    output["hymt2_adapter_version"] = ADAPTER_VERSION
    output["hymt2_translated_json"] = translated_json_path
    output["hymt2_applied_items"] = applied_items
    output["hymt2_applied_fields"] = applied_fields_total
    return output


def main() -> int:
    args = parse_args()
    source_data = load_json(args.source_json)
    translated_data = load_json(args.translated_json)
    output = build_output(source_data, translated_data, args.translated_json)
    write_json(args.output, output)
    print(f"written: {args.output}")
    print(f"hymt2_applied_items: {output['hymt2_applied_items']}")
    print(f"hymt2_applied_fields: {output['hymt2_applied_fields']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

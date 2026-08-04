#!/usr/bin/env python3
"""Deterministic gate for Lazyweb Reference Log drafts.

The LLM may create only the temporary draft returned by ``prepare``. This
program owns state checks, validation, publication, the run manifest/log, and
the final PROCESSED marker.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


KL_TZ = timezone(timedelta(hours=8))
SCHEMA_VERSION = 1
TEMPLATE_PATH = Path("lazyweb/template/reference-log-template.md")
SKILL_PATH = Path(".agents/skills/lazyweb-reference-log/SKILL.md")
INBOX_PATH = Path("lazyweb/inbox")
OUTPUT_PATH = Path("lazyweb/output")
LOGS_PATH = Path("lazyweb/logs")
INPUT_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-(?P<slug>.+)$")
URL_RE = re.compile(r"(?i)\b(?:https?://|mcp://)[^\s<>{}\[\]\"'`]+")
HEADING_RE = re.compile(r"^(#{1,6}) (.+)$", re.MULTILINE)
BULLET_LABEL_RE = re.compile(r"^- ([^`:\n]{1,80}):", re.MULTILINE)
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|secret)\s*[:=]\s*[^\s]{8,}"),
)
SIGNED_QUERY_KEYS = re.compile(
    r"(?i)(?:[?&](?:x-amz-(?:signature|credential|security-token)|signature|sig|token|access_token|expires)=)"
)
IMAGE_URL_RE = re.compile(r"(?i)\.(?:png|jpe?g|gif|webp|svg|avif)(?:[?#]|$)")
AFFIRMATIVE_COPY_RE = re.compile(
    r"(?:ロゴ|実在(?:ブランド|媒体|店舗|人物|アプリ)|独自UI|固有レイアウト)"
    r".{0,24}(?:を)?(?:コピーする|模写する|再現する|そのまま使う|使用する)"
)
READABLE_CONTENT_RE = re.compile(
    r"読める(?:文字|文言|ラベル).{0,20}(?:数字.{0,12})?(?:を)?(?:入れる|含める|表示する|生成する)"
)


class WorkflowError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def artifact(path: Path, root: Path) -> dict[str, Any]:
    record: dict[str, Any] = {"path": relative(path, root), "sha256": None, "state": "missing"}
    if path.is_symlink():
        record["state"] = "rejected_symlink"
    elif path.is_file():
        record["state"] = "present"
        record["sha256"] = sha256_file(path)
    return record


def context_sha256(root: Path, input_path: Path) -> str:
    records = {
        "article": sha256_file(input_path / "article.md"),
        "research": sha256_file(input_path / "lazyweb-research.md"),
        "template": sha256_file(root / TEMPLATE_PATH),
        "skill": sha256_file(root / SKILL_PATH),
    }
    encoded = json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_now(value: str | None) -> datetime:
    if value is None:
        return datetime.now(KL_TZ).replace(microsecond=0)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(hours=8):
        raise WorkflowError("--now must be ISO 8601 with +08:00")
    return parsed.astimezone(KL_TZ).replace(microsecond=0)


def iso_at(value: datetime) -> str:
    return value.astimezone(KL_TZ).isoformat(timespec="seconds")


def validate_input_path(root: Path, input_arg: str) -> tuple[Path, str, str]:
    given = Path(input_arg)
    if given.is_absolute() or ".." in given.parts:
        raise WorkflowError("input folder must be a project-relative direct child of lazyweb/inbox")
    input_path = root / given
    expected_parent = (root / INBOX_PATH).resolve()
    if input_path.parent.resolve() != expected_parent:
        raise WorkflowError("input folder must be a direct child of lazyweb/inbox")
    match = INPUT_NAME_RE.fullmatch(input_path.name)
    if not match:
        raise WorkflowError("invalid input folder name")
    return input_path, input_path.name, match.group("slug")


def output_paths(root: Path, slug: str, started: datetime) -> tuple[Path, Path]:
    final_output = root / OUTPUT_PATH / f"lazyweb-reference-log-{slug}.md"
    stamp = started.strftime("%Y%m%dT%H%M%S")
    temporary_output = root / OUTPUT_PATH / f".tmp-lazyweb-reference-log-{slug}-{stamp}.md"
    return temporary_output, final_output


def choose_run_paths(root: Path, input_name: str, started: datetime) -> tuple[Path, Path]:
    log_dir = root / LOGS_PATH / input_name
    base = started.strftime("%Y-%m-%d-%H%M%S")
    suffix = ""
    sequence = 1
    while True:
        stem = f"{base}{suffix}"
        run_log = log_dir / f"{stem}.md"
        manifest = log_dir / f"{stem}.manifest.json"
        if not run_log.exists() and not manifest.exists():
            return run_log, manifest
        sequence += 1
        suffix = f"-{sequence:02d}"


def atomic_create(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def read_text(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise WorkflowError(f"required regular file missing: {path}")
    return path.read_text(encoding="utf-8")


def extract_urls(text: str) -> list[str]:
    return URL_RE.findall(text)


def section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.find(marker)
    if start < 0:
        return ""
    next_heading = re.search(r"^## ", text[start + len(marker) :], re.MULTILINE)
    if next_heading is None:
        return text[start:]
    end = start + len(marker) + next_heading.start()
    return text[start:end]


def parse_research_table(text: str) -> tuple[str | None, str | None, list[list[str]]]:
    block = section(text, "Research Items")
    lines = [line.strip() for line in block.splitlines() if line.strip().startswith("|")]
    if len(lines) < 2:
        return None, None, []
    rows: list[list[str]] = []
    for line in lines[2:]:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        rows.append(cells)
    return lines[0], lines[1], rows


def normalized_headings(text: str) -> list[tuple[str, str]]:
    return [(match.group(1), match.group(2)) for match in HEADING_RE.finditer(text)]


def structural_labels(text: str) -> list[str]:
    return BULLET_LABEL_RE.findall(text)


def direction_blocks(text: str) -> list[str]:
    pattern = re.compile(r"^### 案([123])\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    blocks: list[str] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        next_level_two = re.search(r"^## ", text[match.end() : end], re.MULTILINE)
        if next_level_two is not None:
            end = match.end() + next_level_two.start()
        blocks.append(text[match.start() : end])
    return blocks


def article_ngrams(article_text: str) -> set[str]:
    headings = [line.lstrip("#").strip() for line in article_text.splitlines() if line.startswith("#")]
    source = "".join(headings) or article_text[:800]
    normalized = re.sub(r"[^一-龠々ぁ-んァ-ヶーA-Za-z0-9]", "", source)
    ignored = {"今回の記事", "について", "まとめ", "暮らし", "記事では"}
    grams = {normalized[index : index + 4] for index in range(max(0, len(normalized) - 3))}
    return {gram for gram in grams if not any(gram in word for word in ignored)}


def check_result(check_id: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"id": check_id, "passed": bool(passed), "detail": detail}


def validate_draft(root: Path, input_path: Path, draft: Path, final_output: Path) -> dict[str, Any]:
    article_text = read_text(input_path / "article.md")
    research_text = read_text(input_path / "lazyweb-research.md")
    template_text = read_text(root / TEMPLATE_PATH)
    draft_text = read_text(draft)

    template_header, template_separator, template_rows = parse_research_table(template_text)
    draft_header, draft_separator, draft_rows = parse_research_table(draft_text)
    expected_numbers = [row[0] for row in template_rows if row]
    actual_numbers = [row[0] for row in draft_rows if row]
    structure_ok = (
        normalized_headings(template_text) == normalized_headings(draft_text)
        and structural_labels(template_text) == structural_labels(draft_text)
        and template_header == draft_header
        and template_separator == draft_separator
        and expected_numbers == actual_numbers
        and all(len(row) == 8 for row in draft_rows)
    )

    input_urls = set(extract_urls(article_text) + extract_urls(research_text))
    draft_urls = extract_urls(draft_text)
    draft_url_set = set(draft_urls)
    url_subset_ok = draft_url_set.issubset(input_urls)
    url_unchanged_ok = all(url in input_urls for url in draft_urls)
    unsafe_urls = [
        url
        for url in draft_urls
        if url.lower().startswith("mcp://")
        or SIGNED_QUERY_KEYS.search(url)
        or IMAGE_URL_RE.search(url)
        or "@" in url.split("//", 1)[-1].split("/", 1)[0]
    ]

    observations_ok = True
    unknowns_ok = True
    research_item_urls: list[str] = []
    for row in draft_rows:
        if len(row) != 8:
            observations_ok = False
            unknowns_ok = False
            continue
        research_item_urls.extend(extract_urls(row[1]))
        observation = row[4]
        proposal = row[7]
        if observation not in {"要確認", "要確認。"} and not observation.startswith("観察:"):
            observations_ok = False
        if proposal not in {"要確認", "要確認。"} and not proposal.startswith("提案:"):
            observations_ok = False
        if any(not cell for cell in row[2:]):
            unknowns_ok = False

    no_copy_ok = not AFFIRMATIVE_COPY_RE.search(draft_text)
    no_embedded_images_ok = not (
        re.search(r"!\[[^\]]*\]\(", draft_text)
        or re.search(r"(?i)<img\b", draft_text)
        or re.search(r"(?i)data:image/", draft_text)
        or unsafe_urls
    )
    no_signed_urls_ok = not any(SIGNED_QUERY_KEYS.search(url) for url in draft_urls)
    no_secrets_ok = not any(pattern.search(draft_text) for pattern in SECRET_PATTERNS) and not any(
        url.lower().startswith("mcp://") for url in draft_urls
    )

    directions = direction_blocks(draft_text)
    direction_count_ok = len(directions) == 3
    readable_text_ok = direction_count_ok and all(
        re.search(r"読める文字.{0,24}数字.{0,30}(?:含めない|入れない|表示しない)", block)
        and not READABLE_CONTENT_RE.search(block)
        for block in directions
    )
    distinct_ok = direction_count_ok and len({hashlib.sha256(block.encode()).hexdigest() for block in directions}) == 3
    grams = article_ngrams(article_text)
    linked_ok = direction_count_ok and bool(grams) and all(
        any(gram in re.sub(r"\s", "", block) for gram in grams) for block in directions
    )
    abstract_ok = direction_count_ok and all(
        re.search(r"(?:再現しない|コピーしない|模写しない|使わない|含めない)", block)
        and re.search(r"(?:余白|画像外|後から.{0,12}重ね)", block)
        for block in directions
    )

    safety_block = section(draft_text, "Safety Review")
    safety_values = re.findall(r"^- [^:\n]+:\s*(.+)$", safety_block, re.MULTILINE)
    declared_review_ok = len(safety_values) == 5 and all(value.startswith("pass") for value in safety_values)

    checks = [
        check_result("template_structure", structure_ok, "headings, labels, table columns, and row order"),
        check_result("input_url_provenance", url_subset_ok, "every output URL is present verbatim in an input"),
        check_result("url_unchanged", url_unchanged_ok, "adopted URL strings are unchanged"),
        check_result("observation_proposal_separation", observations_ok, "Research Items use explicit observation/proposal prefixes"),
        check_result("unknowns_marked", unknowns_ok, "unknown non-URL fields are not left blank"),
        check_result("no_copy_proposal", no_copy_ok, "no affirmative real-brand/UI/layout copying instruction"),
        check_result("no_embedded_reference_assets", no_embedded_images_ok, "no screenshot, image data, or image URL"),
        check_result("no_signed_urls", no_signed_urls_ok, "no signed URL query keys"),
        check_result("no_secrets_or_mcp", no_secrets_ok, "no credential-shaped value or MCP URL"),
        check_result("no_readable_image_content", readable_text_ok, "all three directions prohibit readable text and numbers"),
        check_result("no_overwrite", not final_output.exists(), "final output is absent at validation time"),
        check_result(
            "three_distinct_article_linked_abstract_directions",
            distinct_ok and linked_ok and abstract_ok and declared_review_ok,
            "three distinct directions link to article language, remain abstract, preserve title space, and declare review pass",
        ),
    ]
    return {
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
        "url_count": len(dict.fromkeys(research_item_urls)),
    }


def status_before_draft(
    root: Path, input_path: Path, slug: str, allowed_temp: Path | None = None
) -> tuple[str, str, Path, list[Path]]:
    _, final_output = output_paths(root, slug, datetime.now(KL_TZ))
    if (input_path / "PROCESSED").exists():
        return "already_processed", "PROCESSED exists", final_output, []
    if not (input_path / "READY").is_file():
        return "processing_failed", "READY missing", final_output, []
    if not (input_path / "article.md").is_file():
        return "missing_article", "article.md missing", final_output, []
    if not (input_path / "lazyweb-research.md").is_file():
        return "missing_research", "lazyweb-research.md missing", final_output, []
    if not (root / TEMPLATE_PATH).is_file():
        return "missing_template", "template missing", final_output, []
    if not (root / SKILL_PATH).is_file():
        return "processing_failed", "skill missing", final_output, []
    if final_output.exists():
        return "blocked_output_exists", "final output exists", final_output, []
    stale = sorted((root / OUTPUT_PATH).glob(f".tmp-lazyweb-reference-log-{slug}-*.md"))
    if allowed_temp is not None:
        stale = [path for path in stale if path.resolve() != allowed_temp.resolve()]
    if stale:
        return "stale_temp_exists", "stale temporary output exists", final_output, stale
    return "ready", "none", final_output, []


def manifest_payload(
    root: Path,
    input_path: Path,
    status: str,
    started: datetime,
    finished: datetime,
    temporary_output: Path | None,
    final_output: Path,
    run_log: Path,
    manifest: Path,
    safety: dict[str, Any] | None,
) -> dict[str, Any]:
    if status == "success":
        output_record = artifact(final_output, root)
    else:
        output_record = {
            "path": relative(final_output, root),
            "sha256": None,
            "state": "existing_not_read" if final_output.exists() else "missing",
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "started_at": iso_at(started),
        "finished_at": iso_at(finished),
        "input_folder": relative(input_path, root),
        "artifacts": {
            "article": artifact(input_path / "article.md", root),
            "research": artifact(input_path / "lazyweb-research.md", root),
            "template": artifact(root / TEMPLATE_PATH, root),
            "skill": artifact(root / SKILL_PATH, root),
            "temporary_output": artifact(temporary_output, root) if temporary_output else None,
            "output": output_record,
        },
        "url_count": int(safety["url_count"]) if safety else 0,
        "safety_review": safety or {"passed": False, "checks": []},
        "run_log": relative(run_log, root),
        "manifest": relative(manifest, root),
    }


def log_text(
    root: Path,
    input_path: Path,
    status: str,
    started: datetime,
    finished: datetime,
    temporary_output: Path | None,
    final_output: Path,
    safety: dict[str, Any] | None,
    reason: str,
) -> str:
    temporary_value = relative(temporary_output, root) if temporary_output else "not_created"
    safety_value = "not_run" if safety is None else ("pass" if safety["passed"] else "fail")
    url_count = int(safety["url_count"]) if safety else 0
    lines = [
        f"status: {status}",
        f"started_at: {iso_at(started)}",
        f"finished_at: {iso_at(finished)}",
        f"input_folder: {relative(input_path, root)}",
        f"template: {TEMPLATE_PATH.as_posix()}",
        f"temporary_output: {temporary_value}",
        f"final_output: {relative(final_output, root)}",
        f"url_count: {url_count}",
        f"safety_review: {safety_value}",
        f"missing_or_stop_reason: {reason}",
    ]
    return "\n".join(lines) + "\n"


def write_run_records(
    root: Path,
    input_path: Path,
    status: str,
    started: datetime,
    temporary_output: Path | None,
    final_output: Path,
    safety: dict[str, Any] | None,
    reason: str,
) -> tuple[Path, Path]:
    finished = datetime.now(KL_TZ).replace(microsecond=0)
    run_log, manifest = choose_run_paths(root, input_path.name, started)
    payload = manifest_payload(
        root, input_path, status, started, finished, temporary_output, final_output, run_log, manifest, safety
    )
    atomic_create(manifest, (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    try:
        atomic_create(
            run_log,
            log_text(
                root, input_path, status, started, finished, temporary_output, final_output, safety, reason
            ).encode("utf-8"),
        )
    except Exception:
        if manifest.is_file():
            manifest.unlink()
        raise
    return run_log, manifest


def prepare(args: argparse.Namespace) -> int:
    root = Path(args.project_root).resolve()
    started = parse_now(args.now)
    try:
        input_path, input_name, slug = validate_input_path(root, args.input_folder)
    except WorkflowError as error:
        print(json.dumps({"status": "processing_failed", "reason": str(error)}, ensure_ascii=False))
        return 2
    temporary_output, _ = output_paths(root, slug, started)
    status, reason, final_output, _ = status_before_draft(root, input_path, slug)
    if status != "ready":
        run_log, manifest = write_run_records(
            root, input_path, status, started, None, final_output, None, reason
        )
        print(
            json.dumps(
                {
                    "status": status,
                    "reason": reason,
                    "run_log": relative(run_log, root),
                    "manifest": relative(manifest, root),
                },
                ensure_ascii=False,
            )
        )
        return 3
    result = {
        "status": "ready",
        "started_at": iso_at(started),
        "input_folder": relative(input_path, root),
        "temporary_output": relative(temporary_output, root),
        "final_output": relative(final_output, root),
        "context_sha256": context_sha256(root, input_path),
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


def restore_after_failed_publication(
    final_output: Path,
    temporary_output: Path,
    expected_hash: str,
    created_records: Iterable[tuple[Path, str]],
) -> None:
    for path, expected in reversed(list(created_records)):
        if path.is_file() and sha256_file(path) == expected:
            path.unlink()
    if final_output.is_file() and sha256_file(final_output) == expected_hash and not temporary_output.exists():
        os.link(final_output, temporary_output)
        final_output.unlink()


def finalize(args: argparse.Namespace) -> int:
    root = Path(args.project_root).resolve()
    input_path, input_name, slug = validate_input_path(root, args.input_folder)
    temporary_output = (root / Path(args.temporary_output)).resolve()
    expected_parent = (root / OUTPUT_PATH).resolve()
    name_match = re.fullmatch(
        rf"\.tmp-lazyweb-reference-log-{re.escape(slug)}-(\d{{8}}T\d{{6}})\.md",
        temporary_output.name,
    )
    if temporary_output.parent != expected_parent or not name_match:
        raise WorkflowError("temporary output path does not match the selected slug")
    started = datetime.strptime(name_match.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=KL_TZ)
    status, reason, final_output, _ = status_before_draft(root, input_path, slug, temporary_output)
    if status != "ready":
        run_log, manifest = write_run_records(
            root,
            input_path,
            status,
            started,
            temporary_output if temporary_output.exists() else None,
            final_output,
            None,
            reason,
        )
        print(json.dumps({"status": status, "run_log": relative(run_log, root), "manifest": relative(manifest, root)}))
        return 3
    if temporary_output.is_symlink() or not temporary_output.is_file():
        raise WorkflowError("temporary output is missing or is not a regular file")

    current_context_sha256 = context_sha256(root, input_path)
    if current_context_sha256 != args.expected_context_sha256:
        run_log, manifest = write_run_records(
            root,
            input_path,
            "processing_failed",
            started,
            temporary_output,
            final_output,
            None,
            "input, template, or skill changed after prepare",
        )
        print(
            json.dumps(
                {
                    "status": "processing_failed",
                    "run_log": relative(run_log, root),
                    "manifest": relative(manifest, root),
                }
            )
        )
        return 5

    safety = validate_draft(root, input_path, temporary_output, final_output)
    if not safety["passed"]:
        failed_ids = [item["id"] for item in safety["checks"] if not item["passed"]]
        reason = "failed checks: " + ",".join(failed_ids)
        run_log, manifest = write_run_records(
            root,
            input_path,
            "safety_review_failed",
            started,
            temporary_output,
            final_output,
            safety,
            reason,
        )
        print(
            json.dumps(
                {
                    "status": "safety_review_failed",
                    "failed_checks": failed_ids,
                    "run_log": relative(run_log, root),
                    "manifest": relative(manifest, root),
                },
                ensure_ascii=False,
            )
        )
        return 4

    output_hash = sha256_file(temporary_output)
    try:
        os.link(temporary_output, final_output)
    except FileExistsError:
        run_log, manifest = write_run_records(
            root,
            input_path,
            "blocked_output_exists",
            started,
            temporary_output,
            final_output,
            None,
            "final output appeared before publication",
        )
        print(json.dumps({"status": "blocked_output_exists", "run_log": relative(run_log, root), "manifest": relative(manifest, root)}))
        return 3
    if sha256_file(final_output) != output_hash:
        raise WorkflowError("published output hash mismatch")
    temporary_output.unlink()

    created_records: list[tuple[Path, str]] = []
    try:
        finished = datetime.now(KL_TZ).replace(microsecond=0)
        run_log, manifest = choose_run_paths(root, input_name, started)
        payload = manifest_payload(
            root,
            input_path,
            "success",
            started,
            finished,
            temporary_output,
            final_output,
            run_log,
            manifest,
            safety,
        )
        manifest_bytes = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        atomic_create(manifest, manifest_bytes)
        created_records.append((manifest, hashlib.sha256(manifest_bytes).hexdigest()))

        log_bytes = log_text(
            root, input_path, "success", started, finished, temporary_output, final_output, safety, "none"
        ).encode("utf-8")
        atomic_create(run_log, log_bytes)
        created_records.append((run_log, hashlib.sha256(log_bytes).hexdigest()))

        processed = input_path / "PROCESSED"
        processed_text = (
            f"processed_at: {iso_at(datetime.now(KL_TZ).replace(microsecond=0))}\n"
            f"output: {relative(final_output, root)}\n"
            f"run_log: {relative(run_log, root)}\n"
        )
        processed_bytes = processed_text.encode("utf-8")
        atomic_create(processed, processed_bytes)
        created_records.append((processed, hashlib.sha256(processed_bytes).hexdigest()))
    except Exception as error:
        restore_after_failed_publication(final_output, temporary_output, output_hash, created_records)
        run_log, manifest = write_run_records(
            root,
            input_path,
            "processing_failed",
            started,
            temporary_output if temporary_output.exists() else None,
            final_output,
            safety,
            f"post-publication record creation failed: {type(error).__name__}",
        )
        print(json.dumps({"status": "processing_failed", "run_log": relative(run_log, root), "manifest": relative(manifest, root)}))
        return 5

    result = {
        "status": "success",
        "final_output": relative(final_output, root),
        "run_log": relative(run_log, root),
        "manifest": relative(manifest, root),
        "processed": relative(processed, root),
        "url_count": safety["url_count"],
        "output_sha256": output_hash,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


def validate_only(args: argparse.Namespace) -> int:
    root = Path(args.project_root).resolve()
    input_path, _, slug = validate_input_path(root, args.input_folder)
    draft = (root / Path(args.draft)).resolve()
    _, final_output = output_paths(root, slug, datetime.now(KL_TZ))
    result = validate_draft(root, input_path, draft, final_output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare", help="check one manual input before drafting")
    prepare_parser.add_argument("--input-folder", required=True)
    prepare_parser.add_argument("--now", help="test-only ISO 8601 +08:00 clock injection")
    prepare_parser.set_defaults(function=prepare)

    validate_parser = subparsers.add_parser("validate", help="validate a draft without publishing")
    validate_parser.add_argument("--input-folder", required=True)
    validate_parser.add_argument("--draft", required=True)
    validate_parser.set_defaults(function=validate_only)

    finalize_parser = subparsers.add_parser("finalize", help="validate and publish a prepared draft")
    finalize_parser.add_argument("--input-folder", required=True)
    finalize_parser.add_argument("--temporary-output", required=True)
    finalize_parser.add_argument("--expected-context-sha256", required=True)
    finalize_parser.set_defaults(function=finalize)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.function(args))
    except (OSError, UnicodeError, WorkflowError, ValueError) as error:
        print(json.dumps({"status": "processing_failed", "reason": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

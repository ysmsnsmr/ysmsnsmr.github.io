#!/usr/bin/env python3
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from validate_malaysia_groq_merged_candidate import validate_candidate


DEFAULT_OUTPUT_DIR = Path("/tmp/malaysia_phase2b13_groq_merged_rehearsal")
DEFAULT_MODEL = "llama-3.3-70b-versatile"
TARGET_DATELINE_RE = re.compile(
    r"(KUALA LUMPUR,|PUTRAJAYA,|GEORGE TOWN,|MELAKA,|— The|appeared first|The post|::inbox-item|Lowyat|lowyat)"
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_command(args: list[str], stdout_path: Path, stderr_path: Path) -> int:
    with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open("w", encoding="utf-8") as stderr_file:
        completed = subprocess.run(args, stdout=stdout_file, stderr=stderr_file, text=True)
    return completed.returncode


def markdown_urls(markdown: str) -> list[str]:
    return re.findall(r"出典元URL：(\S+)", markdown)


def markdown_has_required_lines(markdown: str) -> dict[str, bool]:
    return {
        "has_category_headers": all(header in markdown for header in ["【速報】", "【生活インパクト】", "【知っておくと得】"]),
        "has_processed_count": "処理対象件数：" in markdown,
        "has_selected_count": "要約対象件数：" in markdown,
        "has_failed_sources_line": "失敗したソース一覧：" in markdown,
    }


def selected_urls(selected_json: dict[str, Any]) -> list[str]:
    items = selected_json.get("items", [])
    if not isinstance(items, list):
        return []
    return [item.get("link", "") for item in items if isinstance(item, dict) and item.get("link")]


def build_report(
    output_dir: Path,
    rss_rc: int,
    groq_rc: int | None,
    live_groq_executed: bool,
    model: str,
) -> dict[str, Any]:
    selected_json = read_json(output_dir / "selected_items.json")
    improved_json = read_json(output_dir / "groq_llama_improved_items.json")
    candidate_markdown = read_text(output_dir / "groq_merged_candidate.md")
    stderr_text = read_text(output_dir / "groq_stderr.log")

    selected = selected_urls(selected_json)
    rendered = markdown_urls(candidate_markdown)
    selected_set = set(selected)
    rendered_set = set(rendered)
    dateline_matches = sorted(set(TARGET_DATELINE_RE.findall(candidate_markdown)))
    numeric_fallback_lines = [line for line in stderr_text.splitlines() if "unsafe numeric unit conversion" in line]
    required_lines = markdown_has_required_lines(candidate_markdown)
    validator_status = validate_candidate(
        output_dir / "selected_items.json",
        output_dir / "production_candidate_rehearsal.md",
        output_dir / "groq_llama_improved_items.json",
        output_dir / "rss.md",
    )

    return {
        "schema_version": "malaysia-groq-merged-rehearsal/v1",
        "generated_at": datetime.now().astimezone().isoformat(),
        "output_dir": str(output_dir),
        "model": model,
        "live_groq_executed": live_groq_executed,
        "rss_command_returncode": rss_rc,
        "groq_command_returncode": groq_rc,
        "counts": {
            "processed": selected_json.get("counts", {}).get("processed"),
            "selected": selected_json.get("counts", {}).get("selected"),
            "failed_sources": selected_json.get("counts", {}).get("failed_sources"),
            "groq_requested": improved_json.get("counts", {}).get("requested"),
            "groq_accepted": improved_json.get("counts", {}).get("accepted"),
            "groq_fallback": improved_json.get("counts", {}).get("fallback"),
        },
        "url_validation": {
            "selected_url_count": len(selected),
            "rendered_url_count": len(rendered),
            "missing_selected_urls": sorted(selected_set - rendered_set),
            "extra_rendered_urls": sorted(rendered_set - selected_set),
        },
        "markdown_validation": {
            **required_lines,
            "target_dateline_matches": dateline_matches,
            "numeric_unit_fallback_lines": numeric_fallback_lines,
        },
        "production_boundary": {
            "wrote_news_malaysia": False,
            "candidate_output": str(output_dir / "production_candidate_rehearsal.md"),
        },
        "conditional_overwrite_validator": {
            "passed": validator_status.get("passed"),
            "failures": validator_status.get("failures", []),
            "status": validator_status,
        },
    }


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    counts = report["counts"]
    url_validation = report["url_validation"]
    markdown_validation = report["markdown_validation"]
    boundary = report["production_boundary"]
    validator = report["conditional_overwrite_validator"]
    lines = [
        "# Phase 2B.13 Groq Merged Production Rehearsal Report",
        "",
        f"- generated_at: {report['generated_at']}",
        f"- output_dir: {report['output_dir']}",
        f"- model: {report['model']}",
        f"- live_groq_executed: {str(report['live_groq_executed']).lower()}",
        f"- rss_command_returncode: {report['rss_command_returncode']}",
        f"- groq_command_returncode: {report['groq_command_returncode']}",
        "",
        "## Counts",
        "",
        f"- processed: {counts.get('processed')}",
        f"- selected: {counts.get('selected')}",
        f"- failed_sources: {counts.get('failed_sources')}",
        f"- groq_requested: {counts.get('groq_requested')}",
        f"- groq_accepted: {counts.get('groq_accepted')}",
        f"- groq_fallback: {counts.get('groq_fallback')}",
        "",
        "## Validation",
        "",
        f"- selected_url_count: {url_validation['selected_url_count']}",
        f"- rendered_url_count: {url_validation['rendered_url_count']}",
        f"- missing_selected_urls: {len(url_validation['missing_selected_urls'])}",
        f"- extra_rendered_urls: {len(url_validation['extra_rendered_urls'])}",
        f"- has_category_headers: {markdown_validation['has_category_headers']}",
        f"- has_processed_count: {markdown_validation['has_processed_count']}",
        f"- has_selected_count: {markdown_validation['has_selected_count']}",
        f"- has_failed_sources_line: {markdown_validation['has_failed_sources_line']}",
        f"- target_dateline_matches: {', '.join(markdown_validation['target_dateline_matches']) or 'none'}",
        f"- numeric_unit_fallback_lines: {len(markdown_validation['numeric_unit_fallback_lines'])}",
        f"- conditional_overwrite_validator_passed: {validator['passed']}",
        f"- conditional_overwrite_validator_failures: {len(validator['failures'])}",
        "",
        "## Boundary",
        "",
        f"- wrote_news_malaysia: {boundary['wrote_news_malaysia']}",
        f"- production_candidate_rehearsal: {boundary['candidate_output']}",
        "- production_adoption: not approved in Phase 2B.13",
        "",
    ]
    if validator["failures"]:
        lines.extend(["## Conditional Overwrite Validator Failures", ""])
        lines.extend(f"- {failure}" for failure in validator["failures"])
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Write rehearsal artifacts under this directory.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Groq model for the rehearsal.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rss_md = output_dir / "rss.md"
    selected_json = output_dir / "selected_items.json"
    groq_md = output_dir / "groq_merged_candidate.md"
    candidate_md = output_dir / "production_candidate_rehearsal.md"
    improved_json = output_dir / "groq_llama_improved_items.json"

    rss_rc = run_command(
        [
            sys.executable,
            "-B",
            "scripts/malaysia_rss_summary.py",
            "--include-paul-tan",
            "--diagnostics",
            "--output",
            str(rss_md),
            "--json-output",
            str(selected_json),
        ],
        output_dir / "rss_stdout.log",
        output_dir / "rss_stderr.log",
    )

    live_groq_executed = bool(os.environ.get("GROQ_API_KEY"))
    groq_rc: int | None = None
    if rss_rc != 0:
        groq_md.write_text("", encoding="utf-8")
        write_json(
            improved_json,
            {
                "schema_version": "malaysia-groq-improved-items/v1",
                "generated_at": datetime.now().astimezone().isoformat(),
                "model": args.model,
                "counts": {"requested": 0, "accepted": 0, "fallback": 0},
                "items": [],
            },
        )
        (output_dir / "groq_stdout.log").write_text("", encoding="utf-8")
        (output_dir / "groq_stderr.log").write_text("RSS generation failed; live Groq rehearsal not executed.\n", encoding="utf-8")
    elif live_groq_executed:
        groq_rc = run_command(
            [
                sys.executable,
                "-B",
                "scripts/render_malaysia_news_with_groq.py",
                "--json-input",
                str(selected_json),
                "--rss-markdown-input",
                str(rss_md),
                "--output",
                str(groq_md),
                "--model",
                args.model,
                "--debug-groq",
                "--improved-items-output",
                str(improved_json),
                "--merge-accepted-with-rss-markdown",
            ],
            output_dir / "groq_stdout.log",
            output_dir / "groq_stderr.log",
        )
    else:
        shutil.copyfile(rss_md, groq_md)
        write_json(
            improved_json,
            {
                "schema_version": "malaysia-groq-improved-items/v1",
                "generated_at": datetime.now().astimezone().isoformat(),
                "model": args.model,
                "counts": {"requested": 0, "accepted": 0, "fallback": 0},
                "items": [],
            },
        )
        (output_dir / "groq_stdout.log").write_text("", encoding="utf-8")
        (output_dir / "groq_stderr.log").write_text("GROQ_API_KEY is not set; live Groq rehearsal not executed.\n", encoding="utf-8")

    shutil.copyfile(groq_md, candidate_md)

    report = build_report(output_dir, rss_rc, groq_rc, live_groq_executed, args.model)
    write_json(output_dir / "rehearsal_report.json", report)
    write_markdown_report(output_dir / "rehearsal_report.md", report)

    print(f"Wrote rehearsal artifacts: {output_dir}")
    print(f"Wrote report: {output_dir / 'rehearsal_report.md'}")
    return 0 if rss_rc == 0 and (groq_rc in (None, 0)) else 1


if __name__ == "__main__":
    raise SystemExit(main())

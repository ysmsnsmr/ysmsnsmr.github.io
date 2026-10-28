#!/usr/bin/env python3
"""Build a public Cloudflare Pages mirror of Malaysia News."""

import argparse
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "news" / "malaysia"
OUTPUT = ROOT / "cloudflare-malaysia-news-dist"
DAILY_FILE = re.compile(r"\d{4}-\d{2}-\d{2}\.(?:html|md)\Z")
REQUIRED_FILES = ("index.html", "location-map.js")


def build(source: Path, output: Path) -> int:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("News directory is missing or a symbolic link")
    if output.is_symlink() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
        raise ValueError("Output directory must be empty")
    names = list(REQUIRED_FILES)
    names.extend(sorted(path.name for path in source.iterdir() if DAILY_FILE.fullmatch(path.name)))
    if not any(name.endswith(".html") and DAILY_FILE.fullmatch(name) for name in names):
        raise ValueError("No daily news pages found")
    for name in names:
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Public file missing or symbolic link: {name}")
    target = output / "news" / "malaysia"
    target.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copyfile(source / name, target / name)
    (output / "_redirects").write_text("/ /news/malaysia/ 302\n", encoding="utf-8")
    print(f"Built {len(names)} Malaysia News public files in {output}")
    return len(names)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    try:
        build(SOURCE, args.output)
    except ValueError as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()

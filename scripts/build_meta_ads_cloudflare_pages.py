#!/usr/bin/env python3
"""Build a minimal, noindex Cloudflare Pages mirror of the Meta Ads feed."""

import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "cloudflare-meta-ads-dist"
FILES = (
    "index.html", "detail.html", "style.css", "favorites.js",
    "localized-feed.js", "localized-detail.js", "personal-feed.json",
    "demo-latest.json", "latest.json", "ja/index.html", "ja/detail.html",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    output = parser.parse_args().output
    if output.is_symlink() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
        raise SystemExit("Output directory must be empty")
    target = output / "meta-ads-updates"
    target.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        source = ROOT / "meta-ads-updates" / name
        if source.is_symlink() or not source.is_file():
            raise SystemExit(f"Required public file missing or symbolic link: {name}")
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    (output / "_headers").write_text("/*\n  X-Robots-Tag: noindex, nofollow\n", encoding="utf-8")
    (output / "404.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="robots" content="noindex"><title>Not found</title>'
        '<h1>Page not found</h1><p><a href="/meta-ads-updates/">Meta Ads Update Feed</a></p></html>\n',
        encoding="utf-8",
    )
    print(f"Built {len(FILES)} allowlisted public files in {output}")


if __name__ == "__main__":
    main()

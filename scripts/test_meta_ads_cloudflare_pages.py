import subprocess
import sys
import tempfile
import unittest
import json
import struct
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "build_meta_ads_cloudflare_pages.py"


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "link":
            self.links.append(dict(attrs))


class CloudflareBuildTest(unittest.TestCase):
    def test_output_is_allowlisted_and_does_not_overwrite_existing_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            subprocess.run([sys.executable, str(SCRIPT), "--output", str(output)], check=True)
            names = {str(path.relative_to(output)) for path in output.rglob("*") if path.is_file()}
            self.assertEqual(names, {
                "404.html", "_headers", "meta-ads-updates/index.html", "meta-ads-updates/detail.html",
                "meta-ads-updates/ja/index.html", "meta-ads-updates/ja/detail.html",
                "meta-ads-updates/tags.html", "meta-ads-updates/ja/tags.html", "meta-ads-updates/tag-catalog.js", "meta-ads-updates/tags.js",
                "meta-ads-updates/style.css", "meta-ads-updates/favorites.js",
                "meta-ads-updates/localized-feed.js", "meta-ads-updates/localized-detail.js",
                "meta-ads-updates/personal-feed.json", "meta-ads-updates/demo-latest.json",
                "meta-ads-updates/headline-translations.json",
                "meta-ads-updates/latest.json",
                "meta-ads-updates/feed-icon.svg", "meta-ads-updates/icon-180.png",
                "meta-ads-updates/icon-192.png", "meta-ads-updates/icon-512.png",
                "meta-ads-updates/manifest.webmanifest", "meta-ads-updates/ja/manifest.webmanifest",
            })
            self.assertIn("X-Robots-Tag: noindex", (output / "_headers").read_text())
            self.assertEqual((output / "meta-ads-updates/personal-feed.json").read_bytes(),
                             (ROOT / "meta-ads-updates/personal-feed.json").read_bytes())
            result = subprocess.run([sys.executable, str(SCRIPT), "--output", str(output)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)

    def test_home_icons_and_manifests_resolve_in_both_locales(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            subprocess.run([sys.executable, str(SCRIPT), "--output", str(output)], check=True)
            for page in ("meta-ads-updates/index.html", "meta-ads-updates/ja/index.html"):
                with self.subTest(page=page):
                    page_url = "https://example.test/" + page.removesuffix("index.html")
                    parser = LinkParser()
                    parser.feed((output / page).read_text())
                    links = {link.get("rel"): link.get("href") for link in parser.links if link.get("rel") in ("manifest", "apple-touch-icon")}
                    self.assertEqual(set(links), {"manifest", "apple-touch-icon"})
                    for link in parser.links:
                        if link.get("rel") not in ("icon", "apple-touch-icon", "manifest"):
                            continue
                        path = urlparse(urljoin(page_url, link["href"])).path.lstrip("/")
                        self.assertTrue((output / path).is_file(), path)
                    manifest_url = urljoin(page_url, links["manifest"])
                    manifest = json.loads((output / urlparse(manifest_url).path.lstrip("/")).read_text())
                    self.assertEqual(urljoin(manifest_url, manifest["start_url"]), page_url)
                    self.assertEqual(manifest["display"], "browser")
                    for icon in manifest["icons"]:
                        path = urlparse(urljoin(manifest_url, icon["src"])).path.lstrip("/")
                        image = (output / path).read_bytes()
                        self.assertEqual(image[:8], b"\x89PNG\r\n\x1a\n")
                        width, height = struct.unpack(">II", image[16:24])
                        self.assertEqual(f"{width}x{height}", icon["sizes"])
                    apple = (output / urlparse(urljoin(page_url, links["apple-touch-icon"])).path.lstrip("/")).read_bytes()
                    self.assertEqual(struct.unpack(">II", apple[16:24]), (180, 180))


if __name__ == "__main__":
    unittest.main()

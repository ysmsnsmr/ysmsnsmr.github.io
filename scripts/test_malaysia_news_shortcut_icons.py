"""Static shortcut metadata and assets must work on both hosting layouts."""

from html.parser import HTMLParser
import json
from pathlib import Path
import struct
import tempfile
import unittest
from urllib.parse import urljoin

import build_malaysia_cloudflare_pages as mirror
import build_malaysia_news_index as builder


class HeadParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.meta = {}

    def handle_starttag(self, tag, attributes):
        values = dict(attributes)
        if tag == "link": self.links.append(values)
        if tag == "meta": self.meta[values.get("name")] = values.get("content")


class ShortcutIconTests(unittest.TestCase):
    def test_png_sizes_and_opaque_format(self):
        for name, size in (("favicon-32-v1.png", 32), ("apple-touch-icon-152-v1.png", 152),
                           ("apple-touch-icon-167-v1.png", 167), ("apple-touch-icon-180-v1.png", 180),
                           ("icon-192-v1.png", 192), ("icon-512-v1.png", 512)):
            with self.subTest(name=name):
                image = (mirror.SOURCE / name).read_bytes()
                self.assertEqual(image[:8], b"\x89PNG\r\n\x1a\n")
                self.assertEqual(struct.unpack(">II", image[16:24]), (size, size))
                self.assertEqual(image[25], 2)  # RGB, without transparency.

    def test_manifest_launches_news_not_dated_archive_and_has_no_new_app_mode(self):
        manifest = json.loads((mirror.SOURCE / "site.webmanifest").read_text())
        for host in ("https://malaysia-seikatsu-news.pages.dev", "https://ysmsnsmr.github.io"):
            base = host + "/news/malaysia/site.webmanifest"
            self.assertEqual(urljoin(base, manifest["start_url"]), host + "/news/malaysia/")
            self.assertEqual(urljoin(base, manifest["scope"]), host + "/news/malaysia/")
        self.assertEqual(manifest["display"], "browser")
        self.assertEqual(manifest["short_name"], "MY生活ニュース")
        self.assertTrue(any("maskable" in icon.get("purpose", "") for icon in manifest["icons"]))
        for icon in manifest["icons"]:
            self.assertTrue((mirror.SOURCE / icon["src"]).is_file())

    def test_home_daily_and_archive_include_the_same_metadata(self):
        source = next(mirror.SOURCE.glob("????-??-??.md"))
        day = builder.parse_markdown(source)
        for page in (builder.render_daily_page(day, is_home=True), builder.render_daily_page(day), builder.render_html([day])):
            head = HeadParser()
            head.feed(page)
            self.assertEqual(head.meta["apple-mobile-web-app-title"], "MY生活ニュース")
            self.assertEqual(head.meta["theme-color"], "#006b5f")
            self.assertEqual(len([link for link in head.links if link.get("rel") == "manifest"]), 1)
            self.assertEqual(len([link for link in head.links if link.get("rel") == "apple-touch-icon"]), 3)
            self.assertNotIn("serviceWorker.register", page)
            for link in head.links:
                if link.get("rel") in {"icon", "apple-touch-icon", "manifest"}:
                    self.assertTrue((mirror.SOURCE / link["href"]).is_file())

    def test_cloudflare_root_and_nested_pages_have_reachable_icon_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            mirror.build(mirror.SOURCE, output)
            for file in (output / "index.html", output / "news/malaysia/index.html", output / "news/malaysia/archive.html"):
                head = HeadParser()
                head.feed(file.read_text())
                for link in head.links:
                    if link.get("rel") in {"icon", "apple-touch-icon", "manifest"}:
                        base = "https://example.test/" + file.relative_to(output).as_posix()
                        resolved = urljoin(base, link["href"]).split("https://example.test/", 1)[1]
                        self.assertTrue((output / resolved).is_file())


if __name__ == "__main__":
    unittest.main()

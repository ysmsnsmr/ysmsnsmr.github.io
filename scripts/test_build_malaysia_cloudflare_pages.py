import re
import tempfile
import unittest
from pathlib import Path
import build_malaysia_cloudflare_pages as mirror


class MalaysiaCloudflareBuildTests(unittest.TestCase):
    def test_only_public_files_are_copied_and_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            for name in ("index.html", "archive.html", "location-map.js", "daily-page.js", "2026-10-28.html", "2026-10-28.md", "private.json"):
                (source / name).write_text(name, encoding="utf-8")
            (source / "index.html").write_text('<a href="./archive.html">archive</a><a href="#article-1">article</a><script src="./daily-page.js"></script>', encoding="utf-8")
            output = root / "output"
            self.assertEqual(mirror.build(source, output), 6)
            target = output / "news" / "malaysia"
            self.assertEqual({path.name for path in target.iterdir()},
                             {"index.html", "archive.html", "location-map.js", "daily-page.js", "2026-10-28.html", "2026-10-28.md"})
            root_home = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn('href="/news/malaysia/archive.html"', root_home)
            self.assertIn('href="#article-1"', root_home)
            self.assertIn('src="/news/malaysia/daily-page.js"', root_home)
            self.assertFalse((output / "_redirects").exists())
            self.assertFalse((output / "_headers").exists())
            with self.assertRaises(ValueError):
                mirror.build(source, output)
            self.assertEqual((target / "index.html").read_text(), (source / "index.html").read_text())

    def test_symbolic_links_and_missing_required_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "index.html").write_text("index", encoding="utf-8")
            (source / "2026-10-28.html").write_text("news", encoding="utf-8")
            with self.assertRaises(ValueError):
                mirror.build(source, root / "missing")
            (source / "location-map.js").symlink_to(source / "index.html")
            with self.assertRaises(ValueError):
                mirror.build(source, root / "symlink")

    def test_current_index_and_latest_day_links_are_packaged(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            mirror.build(mirror.SOURCE, output)
            target = output / "news" / "malaysia"
            index = (target / "index.html").read_text(encoding="utf-8")
            for name in re.findall(r'href="\./(\d{4}-\d{2}-\d{2}\.(?:html|md))"', index):
                self.assertTrue((target / name).is_file(), name)
            self.assertTrue((target / "location-map.js").is_file())
            self.assertTrue((target / "daily-page.js").is_file())
            self.assertTrue((target / "archive.html").is_file())
            self.assertIn('href="/news/malaysia/archive.html"', (output / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

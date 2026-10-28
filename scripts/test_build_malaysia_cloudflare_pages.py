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
            for name in ("index.html", "location-map.js", "2026-10-28.html", "2026-10-28.md", "private.json"):
                (source / name).write_text(name, encoding="utf-8")
            output = root / "output"
            self.assertEqual(mirror.build(source, output), 4)
            target = output / "news" / "malaysia"
            self.assertEqual({path.name for path in target.iterdir()},
                             {"index.html", "location-map.js", "2026-10-28.html", "2026-10-28.md"})
            self.assertEqual((output / "_redirects").read_text(), "/ /news/malaysia/ 302\n")
            self.assertFalse((output / "_headers").exists())
            with self.assertRaises(ValueError):
                mirror.build(source, output)
            self.assertEqual((target / "index.html").read_text(), "index.html")

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


if __name__ == "__main__":
    unittest.main()

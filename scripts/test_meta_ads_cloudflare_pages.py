import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "build_meta_ads_cloudflare_pages.py"


class CloudflareBuildTest(unittest.TestCase):
    def test_output_is_allowlisted_and_does_not_overwrite_existing_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            subprocess.run([sys.executable, str(SCRIPT), "--output", str(output)], check=True)
            names = {str(path.relative_to(output)) for path in output.rglob("*") if path.is_file()}
            self.assertEqual(names, {
                "404.html", "_headers", "meta-ads-updates/index.html", "meta-ads-updates/detail.html",
                "meta-ads-updates/ja/index.html", "meta-ads-updates/ja/detail.html",
                "meta-ads-updates/style.css", "meta-ads-updates/favorites.js",
                "meta-ads-updates/localized-feed.js", "meta-ads-updates/localized-detail.js",
                "meta-ads-updates/personal-feed.json", "meta-ads-updates/demo-latest.json",
                "meta-ads-updates/latest.json",
            })
            self.assertIn("X-Robots-Tag: noindex", (output / "_headers").read_text())
            self.assertEqual((output / "meta-ads-updates/personal-feed.json").read_bytes(),
                             (ROOT / "meta-ads-updates/personal-feed.json").read_bytes())
            result = subprocess.run([sys.executable, str(SCRIPT), "--output", str(output)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()

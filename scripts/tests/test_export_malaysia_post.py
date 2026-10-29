import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_malaysia_post import convert


class ExportPostTest(unittest.TestCase):
    def test_articles_and_source_only(self):
        text = '''更新時点：2026-10-28T07:14:12+08:00
【暮らしに関わる更新】
- 見出し：見出し
- 短見出し：短い
- 概要：概要です。
- 出典：媒体（2026年10月27日）
- 出典元URL：https://example.com/a
【原文のみ】
- 原題：Original title
- 出典：Example
- 出典元URL：https://example.com/b
処理対象件数：2件
'''
        result = convert(text)
        self.assertIn('2026年10月28日 07:14 MYT 時点', result)
        self.assertIn('### 見出し\n\n概要です。', result)
        self.assertIn('[媒体（2026年10月27日）](<https://example.com/a>)', result)
        self.assertIn('### Original title', result)
        self.assertNotIn('処理対象件数', result)
        self.assertNotIn('短い', result)

    def test_incomplete_and_unknown_are_errors(self):
        with self.assertRaises(ValueError):
            convert('【暮らし】\n- 見出し：記事\n- 概要：内容\n')
        with self.assertRaises(ValueError):
            convert('【暮らし】\n- 見出し：記事\n- 未知：値\n')


if __name__ == '__main__':
    unittest.main()

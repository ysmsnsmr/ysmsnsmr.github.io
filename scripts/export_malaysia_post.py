#!/usr/bin/env python3
"""Convert a daily Malaysia News Markdown file to reader-facing Markdown."""

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit


def convert(text: str) -> str:
    output = []
    item = {}
    category = None
    count = 0

    def flush():
        nonlocal item, count
        if not item:
            return
        title = item.get('見出し') or item.get('短見出し') or item.get('原題')
        source, url = item.get('出典'), item.get('出典元URL')
        if not category or not title or not source or not url:
            raise ValueError('記事の見出し・カテゴリ・出典・URLが不足しています')
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or re.search(r'\s', url):
            raise ValueError('出典URLが不正です')
        output.extend([f'### {title}', ''])
        if item.get('概要'):
            output.extend([item['概要'], ''])
        for extra in item.get('補足', []):
            output.extend([extra, ''])
        safe_source = source.replace('\\', '\\\\').replace('[', '\\[').replace(']', '\\]')
        safe_url = url.replace('(', '%28').replace(')', '%29')
        output.extend([f'[{safe_source}](<{safe_url}>)', ''])
        count += 1
        item = {}

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith('更新時点：'):
            try:
                dt = datetime.fromisoformat(line.split('：', 1)[1])
                if dt.tzinfo is None:
                    raise ValueError
                dt = dt.astimezone(timezone(timedelta(hours=8)))
                output.extend([f'{dt.year}年{dt.month}月{dt.day}日 {dt:%H:%M} MYT 時点', ''])
            except ValueError as exc:
                raise ValueError('更新時点を読み取れません') from exc
        elif re.fullmatch(r'【[^】]+】', line):
            flush()
            category = line[1:-1]
            output.extend([f'## {category}', ''])
        elif line.startswith('- ') and '：' in line:
            key, value = line[2:].split('：', 1)
            if key in ('見出し', '原題'):
                flush()
            if key == '補足':
                item.setdefault(key, []).append(value.strip())
            elif key in ('見出し', '短見出し', '概要', '原題', '出典', '出典元URL'):
                if key in item:
                    raise ValueError(f'記事内に重複する項目があります: {key}')
                item[key] = value.strip()
            else:
                raise ValueError(f'未対応の記事項目です: {key}')
        elif line.startswith(('処理対象件数：', '要約対象件数：', '失敗したソース一覧：')):
            flush()
        else:
            raise ValueError(f'未対応の入力行: {line[:80]}')
    flush()
    if not count:
        raise ValueError('記事が見つかりません')
    return '\n'.join(output).rstrip() + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='日次Markdownのパス')
    args = parser.parse_args()
    try:
        result = convert(args.input.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        print(f'変換できません: {exc}', file=sys.stderr)
        return 1
    sys.stdout.write(result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

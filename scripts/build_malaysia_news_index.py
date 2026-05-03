from __future__ import annotations
#!/usr/bin/env python3
import html
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


MYT = timezone(timedelta(hours=8))
NEWS_DIR = Path("news/malaysia")
OUTPUT_PATH = NEWS_DIR / "index.html"
CATEGORIES = ("【速報】", "【生活インパクト】", "【知っておくと得】")


@dataclass
class NewsDay:
    date: str
    path: Path
    conclusions: list[str]
    category_counts: dict[str, int]
    processed_count: str
    summarized_count: str
    failed_sources: str


def extract_label(text: str, label: str) -> str:
    match = re.search(rf"^{re.escape(label)}：(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else "不明"


def parse_markdown(path: Path) -> NewsDay:
    text = path.read_text(encoding="utf-8")
    category_counts = {category: 0 for category in CATEGORIES}
    conclusions: list[str] = []
    current_category = ""

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line in CATEGORIES:
            current_category = line
            continue
        if line.startswith("- 結論："):
            if current_category in category_counts:
                category_counts[current_category] += 1
            conclusions.append((line[len("- 結論："):] if line.startswith("- 結論：") else line).strip())

    return NewsDay(
        date=path.stem,
        path=path,
        conclusions=conclusions,
        category_counts=category_counts,
        processed_count=extract_label(text, "処理対象件数"),
        summarized_count=extract_label(text, "要約対象件数"),
        failed_sources=extract_label(text, "失敗したソース一覧"),
    )


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def relative_link(day: NewsDay) -> str:
    return f"./{esc(day.path.name)}"


def format_date(date_text: str) -> str:
    try:
        parsed = datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        return date_text
    return f"{parsed.year}年{parsed.month}月{parsed.day}日"


def render_counts(day: NewsDay) -> str:
    parts = []
    for category in CATEGORIES:
        label = category.strip("【】")
        parts.append(
            f'<span class="pill"><span>{esc(label)}</span><strong>{day.category_counts.get(category, 0)}</strong></span>'
        )
    return "\n".join(parts)


def render_conclusions(day: NewsDay, limit: int = 3) -> str:
    if not day.conclusions:
        return '<p class="muted">見出しを抽出できませんでした。</p>'
    items = "\n".join(f"<li>{esc(conclusion)}</li>" for conclusion in day.conclusions[:limit])
    return f"<ol>{items}</ol>"


def render_card(day: NewsDay, latest: bool = False) -> str:
    failed = ""
    if day.failed_sources and day.failed_sources != "なし":
        failed = f'<p class="failed">失敗ソース: {esc(day.failed_sources)}</p>'

    classes = "day-card latest" if latest else "day-card"
    return f"""
      <article class="{classes}">
        <div class="card-head">
          <div>
            <p class="eyebrow">Malaysia RSS Summary</p>
            <h2>{esc(format_date(day.date))}</h2>
          </div>
          <a class="open-link" href="{relative_link(day)}">Markdownを開く</a>
        </div>
        <div class="counts">
          {render_counts(day)}
        </div>
        <div class="metrics">
          <span>処理対象: {esc(day.processed_count)}</span>
          <span>要約対象: {esc(day.summarized_count)}</span>
        </div>
        {render_conclusions(day)}
        {failed}
      </article>
    """


def render_archive(days: list[NewsDay]) -> str:
    if not days:
        return '<p class="muted">過去の記事はまだありません。</p>'
    rows = "\n".join(
        f"""
        <li>
          <a href="{relative_link(day)}">{esc(format_date(day.date))}</a>
          <span>{esc(day.summarized_count)} / 失敗ソース: {esc(day.failed_sources)}</span>
        </li>
        """
        for day in days
    )
    return f'<ul class="archive-list">{rows}</ul>'


def render_html(days: list[NewsDay]) -> str:
    generated_at = datetime.now(MYT)
    generated = (
        f"{generated_at.year}年{generated_at.month}月{generated_at.day}日 "
        f"{generated_at.hour:02d}:{generated_at.minute:02d} MYT"
    )
    latest = days[0] if days else None
    recent = days[:7]
    older = days[7:]

    if latest:
        latest_link = f'<a href="{relative_link(latest)}">{esc(format_date(latest.date))}のMarkdownを見る</a>'
        recent_cards = "\n".join(render_card(day, latest=(idx == 0)) for idx, day in enumerate(recent))
    else:
        latest_link = '<span class="muted">まだ記事がありません。</span>'
        recent_cards = '<p class="muted">まだ記事がありません。</p>'

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Malaysia RSSニュース要約</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8f4;
      --panel: #ffffff;
      --ink: #1b2420;
      --muted: #65716c;
      --line: #dce3dd;
      --accent: #006b5f;
      --accent-soft: #e5f3ef;
      --warn: #8f4c00;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.65;
    }}
    main {{
      width: min(1040px, calc(100% - 32px));
      margin: 0 auto;
      padding: 40px 0 56px;
    }}
    header {{
      display: grid;
      gap: 12px;
      margin-bottom: 28px;
    }}
    h1, h2, h3, p {{ margin-top: 0; }}
    h1 {{
      margin-bottom: 4px;
      font-size: clamp(2rem, 5vw, 4rem);
      line-height: 1.05;
      letter-spacing: 0;
    }}
    h2 {{ margin-bottom: 0; font-size: 1.45rem; }}
    h3 {{ margin: 34px 0 14px; font-size: 1.1rem; }}
    a {{ color: var(--accent); text-decoration-thickness: 0.08em; text-underline-offset: 0.18em; }}
    .subhead {{ max-width: 720px; color: var(--muted); }}
    .meta-bar {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px 18px;
      align-items: center;
      color: var(--muted);
      font-size: 0.95rem;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
    }}
    .day-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 18px;
      box-shadow: 0 1px 2px rgba(20, 32, 28, 0.04);
    }}
    .day-card.latest {{
      grid-column: 1 / -1;
      border-color: #9accc1;
      background: linear-gradient(180deg, #ffffff 0%, #f0faf7 100%);
    }}
    .card-head {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
      margin-bottom: 14px;
    }}
    .eyebrow {{
      margin-bottom: 2px;
      color: var(--accent);
      font-size: 0.78rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .open-link {{
      flex: 0 0 auto;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 6px 10px;
      background: #fff;
      font-size: 0.9rem;
      text-decoration: none;
    }}
    .counts {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 12px 0;
    }}
    .pill {{
      display: inline-flex;
      gap: 8px;
      align-items: center;
      border-radius: 999px;
      background: var(--accent-soft);
      padding: 5px 10px;
      font-size: 0.88rem;
    }}
    .metrics {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px 14px;
      margin-bottom: 12px;
      color: var(--muted);
      font-size: 0.9rem;
    }}
    ol {{
      margin: 0;
      padding-left: 1.3rem;
    }}
    li + li {{ margin-top: 6px; }}
    .failed {{
      margin: 14px 0 0;
      color: var(--warn);
      font-weight: 700;
    }}
    .archive-list {{
      list-style: none;
      margin: 0;
      padding: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }}
    .archive-list li {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      padding: 12px 14px;
    }}
    .archive-list li + li {{ border-top: 1px solid var(--line); }}
    .archive-list span {{ color: var(--muted); }}
    .muted {{ color: var(--muted); }}
    @media (max-width: 640px) {{
      main {{ width: min(100% - 20px, 1040px); padding-top: 24px; }}
      .card-head, .archive-list li {{ flex-direction: column; }}
      .open-link {{ align-self: flex-start; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Malaysia RSSニュース要約</h1>
      <p class="subhead">Malay Mail と Astro Awani のRSSから生成した、マレーシア国内ニュースの日次アーカイブです。</p>
      <div class="meta-bar">
        <span>生成日時: {esc(generated)}</span>
        <span>最新: {latest_link}</span>
      </div>
    </header>

    <section aria-labelledby="recent-heading">
      <h3 id="recent-heading">直近7日</h3>
      <div class="cards">
        {recent_cards}
      </div>
    </section>

    <section aria-labelledby="archive-heading">
      <h3 id="archive-heading">それ以前</h3>
      {render_archive(older)}
    </section>
  </main>
</body>
</html>
"""


def main() -> int:
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    days = [
        parse_markdown(path)
        for path in sorted(NEWS_DIR.glob("*.md"), reverse=True)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.stem)
    ]
    OUTPUT_PATH.write_text(render_html(days), encoding="utf-8")
    print(f"Wrote index: {OUTPUT_PATH}")
    print(f"Indexed days: {len(days)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

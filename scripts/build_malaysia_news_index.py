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


def format_count(value: str) -> str:
    if value == "不明" or value.endswith("件"):
        return value
    return f"{value}件"


def render_counts(day: NewsDay) -> str:
    parts = []
    for category in CATEGORIES:
        label = category.strip("【】")
        parts.append(
            f'<span class="count-pill"><span>{esc(label)}</span><strong>{day.category_counts.get(category, 0)}</strong></span>'
        )
    return "\n".join(parts)


def render_conclusions(day: NewsDay, limit: int = 3) -> str:
    if not day.conclusions:
        return '<p class="muted">見出しを抽出できませんでした。</p>'
    items = "\n".join(f"<li>{esc(conclusion)}</li>" for conclusion in day.conclusions[:limit])
    return f"<ol>{items}</ol>"


def render_latest_summary(day: NewsDay, generated: str) -> str:
    failed = ""
    if day.failed_sources and day.failed_sources != "なし":
        failed = f'<p class="failed">失敗ソース: {esc(day.failed_sources)}</p>'

    return f"""
      <article class="today-panel">
        <div class="today-head">
          <div>
            <p class="eyebrow">Today</p>
            <h2>{esc(format_date(day.date))}</h2>
            <p class="muted">生成日時: {esc(generated)}</p>
          </div>
          <a class="primary-link" href="{relative_link(day)}">今日のMarkdownを開く</a>
        </div>
        <div class="today-metrics" aria-label="今日の集計">
          <div>
            <span>処理対象</span>
            <strong>{esc(day.processed_count)}</strong>
          </div>
          <div>
            <span>要約対象</span>
            <strong>{esc(day.summarized_count)}</strong>
          </div>
          <div>
            <span>失敗ソース</span>
            <strong>{esc(day.failed_sources)}</strong>
          </div>
        </div>
        <div class="counts" aria-label="カテゴリ別件数">
          {render_counts(day)}
        </div>
        <div class="today-conclusions">
          <h3>今日の要点</h3>
          {render_conclusions(day)}
        </div>
        {failed}
      </article>
    """


def render_recent_day(day: NewsDay) -> str:
    failed_label = "失敗なし" if day.failed_sources == "なし" else f"失敗: {day.failed_sources}"
    return f"""
        <article class="recent-row">
          <div class="recent-date">
            <p class="eyebrow">Daily</p>
            <h3>{esc(format_date(day.date))}</h3>
          </div>
          <div class="recent-body">
            <div class="counts" aria-label="カテゴリ別件数">
              {render_counts(day)}
            </div>
            {render_conclusions(day, limit=2)}
          </div>
          <div class="recent-actions">
            <span>{esc(format_count(day.summarized_count))} / {esc(failed_label)}</span>
            <a class="open-link" href="{relative_link(day)}">Markdown</a>
          </div>
        </article>
    """


def render_recent(days: list[NewsDay]) -> str:
    if not days:
        return '<p class="muted">比較できる直近日はまだありません。</p>'
    return "\n".join(render_recent_day(day) for day in days)


def render_archive(days: list[NewsDay]) -> str:
    if not days:
        return '<p class="muted">過去の記事はまだありません。</p>'
    rows = "\n".join(
        f"""
        <li>
          <a href="{relative_link(day)}">{esc(format_date(day.date))}</a>
          <span>{esc(format_count(day.summarized_count))}</span>
          <span>{esc(day.failed_sources)}</span>
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
    recent = days[1:7]
    older = days[7:]

    if latest:
        latest_link = f'<a href="{relative_link(latest)}">{esc(format_date(latest.date))}のMarkdownを見る</a>'
        latest_summary = render_latest_summary(latest, generated).strip()
        recent_rows = render_recent(recent).strip()
    else:
        latest_link = '<span class="muted">まだ記事がありません。</span>'
        latest_summary = '<p class="muted">まだ記事がありません。</p>'
        recent_rows = '<p class="muted">まだ記事がありません。</p>'

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Malaysia RSSニュース要約</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f7f4;
      --panel: #ffffff;
      --ink: #1b2420;
      --muted: #65716c;
      --line: #dce3dd;
      --accent: #006b5f;
      --accent-strong: #004c45;
      --accent-soft: #e5f3ef;
      --warn: #8f4c00;
      --shadow: 0 12px 28px rgba(27, 36, 32, 0.07);
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
      width: min(1080px, calc(100% - 32px));
      margin: 0 auto;
      padding: 32px 0 56px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 24px;
      align-items: flex-end;
      margin-bottom: 22px;
    }}
    h1, h2, h3, p {{ margin-top: 0; }}
    h1 {{
      margin-bottom: 8px;
      font-size: clamp(2rem, 4vw, 3.35rem);
      line-height: 1.08;
      letter-spacing: 0;
    }}
    h2 {{
      margin-bottom: 0;
      font-size: clamp(1.65rem, 3vw, 2.4rem);
      line-height: 1.16;
    }}
    h3 {{ margin: 0; font-size: 1rem; line-height: 1.35; }}
    a {{
      color: var(--accent);
      text-decoration-thickness: 0.08em;
      text-underline-offset: 0.18em;
    }}
    a:focus-visible {{
      outline: 3px solid #f4c04d;
      outline-offset: 3px;
      border-radius: 6px;
    }}
    .subhead {{ max-width: 640px; margin-bottom: 0; color: var(--muted); }}
    .meta-bar {{
      display: flex;
      flex-direction: column;
      gap: 6px;
      align-items: flex-end;
      color: var(--muted);
      font-size: 0.95rem;
      text-align: right;
      white-space: nowrap;
    }}
    section + section {{ margin-top: 30px; }}
    .section-head {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: baseline;
      margin-bottom: 12px;
    }}
    .section-head h2 {{
      font-size: 1.08rem;
      line-height: 1.3;
    }}
    .section-head p {{
      margin-bottom: 0;
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .today-panel {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 24px;
      box-shadow: var(--shadow);
    }}
    .today-head {{
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: flex-start;
      margin-bottom: 18px;
    }}
    .today-metrics {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }}
    .today-metrics div {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfa;
      padding: 11px 12px;
    }}
    .today-metrics span {{
      display: block;
      color: var(--muted);
      font-size: 0.78rem;
    }}
    .today-metrics strong {{
      display: block;
      margin-top: 2px;
      color: var(--ink);
      font-size: 1.12rem;
      line-height: 1.2;
    }}
    .today-conclusions {{
      display: grid;
      grid-template-columns: 9rem minmax(0, 1fr);
      gap: 18px;
      align-items: start;
      margin-top: 18px;
      padding-top: 18px;
      border-top: 1px solid var(--line);
    }}
    .today-conclusions h3 {{
      color: var(--accent-strong);
      font-size: 0.95rem;
    }}
    .recent-list {{
      display: grid;
      gap: 10px;
    }}
    .recent-row {{
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: stretch;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 14px;
    }}
    .recent-date {{
      flex: 0 0 9.4rem;
      padding-right: 12px;
      border-right: 1px solid var(--line);
    }}
    .recent-date h3 {{ white-space: nowrap; }}
    .recent-body {{
      flex: 1 1 auto;
      min-width: 0;
    }}
    .recent-actions {{
      flex: 0 0 9rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      align-items: flex-end;
      gap: 12px;
      color: var(--muted);
      font-size: 0.86rem;
      text-align: right;
    }}
    .eyebrow {{
      margin-bottom: 2px;
      color: var(--accent);
      font-size: 0.78rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .primary-link,
    .open-link {{
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 7px 13px;
      background: #fff;
      font-size: 0.9rem;
      line-height: 1.2;
      text-decoration: none;
    }}
    .primary-link {{
      border-color: var(--accent);
      background: var(--accent);
      color: #fff;
      font-weight: 700;
    }}
    .counts {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 0;
    }}
    .count-pill {{
      display: inline-flex;
      gap: 8px;
      align-items: center;
      min-height: 28px;
      border-radius: 999px;
      background: var(--accent-soft);
      padding: 4px 10px;
      font-size: 0.88rem;
    }}
    .count-pill strong {{
      color: var(--accent-strong);
    }}
    .recent-body ol {{
      margin-top: 10px;
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
      display: grid;
      grid-template-columns: minmax(11rem, 1fr) 5rem minmax(8rem, 1fr);
      gap: 12px;
      align-items: center;
      padding: 10px 14px;
    }}
    .archive-list li + li {{ border-top: 1px solid var(--line); }}
    .archive-list span {{ color: var(--muted); }}
    .muted {{ color: var(--muted); }}
    @media (max-width: 640px) {{
      main {{ width: min(100% - 20px, 1080px); padding-top: 24px; }}
      header {{
        display: grid;
        gap: 14px;
        align-items: start;
      }}
      .meta-bar {{
        align-items: flex-start;
        text-align: left;
        white-space: normal;
      }}
      .today-panel {{ padding: 18px; }}
      .today-head {{
        display: grid;
        gap: 14px;
      }}
      .primary-link {{
        width: 100%;
        min-height: 44px;
      }}
      .today-metrics {{
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 6px;
      }}
      .today-metrics div {{ padding: 9px 8px; }}
      .today-metrics strong {{ font-size: 1rem; }}
      .today-conclusions {{
        grid-template-columns: 1fr;
        gap: 10px;
      }}
      .section-head {{
        display: grid;
        gap: 2px;
      }}
      .recent-row {{
        display: grid;
        gap: 12px;
      }}
      .recent-date {{
        flex-basis: auto;
        padding-right: 0;
        padding-bottom: 10px;
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }}
      .recent-actions {{
        flex-basis: auto;
        flex-direction: row;
        align-items: center;
        text-align: left;
      }}
      .open-link {{ min-height: 40px; }}
      .archive-list li {{
        grid-template-columns: 1fr;
        gap: 4px;
        padding: 12px 14px;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Malaysia RSSニュース要約</h1>
        <p class="subhead">Malay Mail と Astro Awani のRSSから生成した、マレーシア国内ニュースの日次ダッシュボードです。</p>
      </div>
      <div class="meta-bar">
        <span>最新: {latest_link}</span>
        <span>更新: {esc(generated)}</span>
      </div>
    </header>

    <section aria-labelledby="today-heading">
      <div class="section-head">
        <h2 id="today-heading">今日のサマリー</h2>
        <p>まず確認したい件数と要点</p>
      </div>
      {latest_summary}
    </section>

    <section aria-labelledby="recent-heading">
      <div class="section-head">
        <h2 id="recent-heading">直近7日の流れ</h2>
        <p>今日を除く直近6日を比較</p>
      </div>
      <div class="recent-list">
        {recent_rows}
      </div>
    </section>

    <section aria-labelledby="archive-heading">
      <div class="section-head">
        <h2 id="archive-heading">それ以前</h2>
        <p>日別Markdownアーカイブ</p>
      </div>
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

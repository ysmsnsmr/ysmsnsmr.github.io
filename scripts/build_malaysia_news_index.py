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
class NewsItem:
    category: str
    conclusion: str = ""
    life_impact: str = ""
    next_action: str = ""
    source: str = ""
    source_url: str = ""

    @property
    def is_display_ready(self) -> bool:
        return bool(self.category and self.conclusion)


@dataclass
class NewsDay:
    date: str
    path: Path
    conclusions: list[str]
    items: list[NewsItem]
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
    items: list[NewsItem] = []
    current_category = ""
    current_item: NewsItem | None = None

    def flush_item() -> None:
        nonlocal current_item
        if current_item and current_item.is_display_ready:
            items.append(current_item)
        current_item = None

    optional_labels = {
        "- 生活への影響：": "life_impact",
        "- 次アクション：": "next_action",
        "- 出典：": "source",
        "- 出典元URL：": "source_url",
    }

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line in CATEGORIES:
            flush_item()
            current_category = line
            continue

        if line.startswith("- 結論："):
            flush_item()
            conclusion = line[len("- 結論：") :].strip()
            if current_category in category_counts:
                category_counts[current_category] += 1
            conclusions.append(conclusion)
            if current_category in CATEGORIES:
                current_item = NewsItem(category=current_category, conclusion=conclusion)
            continue

        if current_item:
            for prefix, field_name in optional_labels.items():
                if line.startswith(prefix):
                    setattr(current_item, field_name, line[len(prefix) :].strip())
                    break

    flush_item()

    return NewsDay(
        date=path.stem,
        path=path,
        conclusions=conclusions,
        items=items,
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


def format_month(date_text: str) -> str:
    try:
        parsed = datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        return "日付不明"
    return f"{parsed.year}年{parsed.month}月"


def format_count(value: str) -> str:
    if value == "不明" or value.endswith("件"):
        return value
    return f"{value}件"


def category_label(category: str) -> str:
    return category.strip("【】")


def failed_label(day: NewsDay) -> str:
    return "失敗なし" if day.failed_sources == "なし" else f"失敗: {day.failed_sources}"


def ordered_items(day: NewsDay) -> list[NewsItem]:
    return [
        item
        for category in CATEGORIES
        for item in day.items
        if item.category == category and item.is_display_ready
    ]


def render_counts(day: NewsDay) -> str:
    parts = []
    for category in CATEGORIES:
        parts.append(
            f'<span class="count-pill"><span>{esc(category_label(category))}</span>'
            f"<strong>{day.category_counts.get(category, 0)}</strong></span>"
        )
    return "\n".join(parts)


def render_conclusions(day: NewsDay, limit: int = 3) -> str:
    if not day.conclusions:
        return '<p class="muted">見出しを抽出できませんでした。</p>'
    items = "\n".join(f"<li>{esc(conclusion)}</li>" for conclusion in day.conclusions[:limit])
    return f"<ol>{items}</ol>"


def render_status_chips(day: NewsDay, generated: str) -> str:
    chips = [
        ("更新", generated),
        ("処理対象", format_count(day.processed_count)),
        ("要約対象", format_count(day.summarized_count)),
        ("失敗ソース", day.failed_sources),
    ]
    status = "\n".join(
        f'<span class="status-chip"><span>{esc(label)}</span><strong>{esc(value)}</strong></span>'
        for label, value in chips
    )
    return f"""
    <div class="status-strip" aria-label="更新状況と集計">
      {status}
      {render_counts(day)}
    </div>
    """


def render_item_card(item: NewsItem) -> str:
    impact = ""
    if item.life_impact:
        impact = f"""
          <div class="item-detail">
            <span>生活への影響</span>
            <p>{esc(item.life_impact)}</p>
          </div>
        """

    action = ""
    if item.next_action:
        action = f"""
          <div class="item-detail">
            <span>次アクション</span>
            <p>{esc(item.next_action)}</p>
          </div>
        """

    source = ""
    if item.source_url:
        source_label = item.source or "出典"
        source = f'<a class="source-link" href="{esc(item.source_url)}">出典: {esc(source_label)}</a>'
    elif item.source:
        source = f'<span class="source-note">出典: {esc(item.source)}</span>'

    return f"""
        <article class="focus-card">
          <p class="item-category">{esc(category_label(item.category))}</p>
          <h3>{esc(item.conclusion)}</h3>
          {impact}
          {action}
          {source}
        </article>
    """


def render_latest_items(day: NewsDay) -> str:
    selected = ordered_items(day)[:3]
    if not selected:
        return f"""
        <div class="fallback-list">
          <h3>今日の要点</h3>
          {render_conclusions(day)}
        </div>
        """
    return "\n".join(render_item_card(item) for item in selected)


def render_latest_summary(day: NewsDay) -> str:
    failed = ""
    if day.failed_sources and day.failed_sources != "なし":
        failed = f'<p class="failed">失敗ソース: {esc(day.failed_sources)}</p>'

    return f"""
      <article class="today-panel">
        <div class="today-head">
          <div>
            <p class="eyebrow">Latest</p>
            <h2>{esc(format_date(day.date))}</h2>
            <p class="muted">カテゴリ順に、既存Markdownの並びを保って表示しています。</p>
          </div>
          <a class="primary-link" href="{relative_link(day)}">今日の全文</a>
        </div>
        <div class="focus-grid">
          {render_latest_items(day)}
        </div>
        {failed}
      </article>
    """


def render_recent_day(day: NewsDay) -> str:
    points = [item.conclusion for item in ordered_items(day)[:2]] or day.conclusions[:2]
    if points:
        point_list = "<ol>" + "\n".join(f"<li>{esc(point)}</li>" for point in points) + "</ol>"
    else:
        point_list = '<p class="muted">見出しを抽出できませんでした。</p>'

    return f"""
        <article class="recent-card">
          <p class="eyebrow">Daily</p>
          <h3>{esc(format_date(day.date))}</h3>
          <div class="counts compact-counts" aria-label="カテゴリ別件数">
            {render_counts(day)}
          </div>
          <div class="recent-body">
            {point_list}
          </div>
          <p class="recent-meta">{esc(format_count(day.summarized_count))} / {esc(failed_label(day))}</p>
          <a class="open-link" href="{relative_link(day)}">日別メモ</a>
        </article>
    """


def render_recent(days: list[NewsDay]) -> str:
    if not days:
        return '<p class="muted">比較できる直近日はまだありません。</p>'
    return "\n".join(render_recent_day(day) for day in days)


def render_archive(days: list[NewsDay]) -> str:
    if not days:
        return '<p class="muted">過去の記事はまだありません。</p>'

    grouped: dict[str, list[NewsDay]] = {}
    for day in days:
        grouped.setdefault(format_month(day.date), []).append(day)

    groups = []
    for index, (month, month_days) in enumerate(grouped.items()):
        rows = "\n".join(
            f"""
            <li>
              <a href="{relative_link(day)}">{esc(format_date(day.date))}</a>
              <span>{esc(format_count(day.summarized_count))}</span>
              <span>{esc(day.failed_sources)}</span>
            </li>
            """
            for day in month_days
        )
        open_attr = " open" if index == 0 else ""
        groups.append(
            f"""
            <details class="archive-month"{open_attr}>
              <summary>
                <span>{esc(month)}</span>
                <span>{len(month_days)}日分</span>
              </summary>
              <ul class="archive-list">
                {rows}
              </ul>
            </details>
            """
        )
    return "\n".join(groups)


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
        latest_summary = render_latest_summary(latest).strip()
        status_chips = render_status_chips(latest, generated).strip()
        recent_rows = render_recent(recent).strip()
        primary_href = relative_link(latest)
    else:
        latest_summary = '<p class="muted">まだ記事がありません。</p>'
        status_chips = '<p class="muted">まだ記事がありません。</p>'
        recent_rows = '<p class="muted">まだ記事がありません。</p>'
        primary_href = "#"

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
    html {{ overflow-x: hidden; }}
    body {{
      margin: 0;
      overflow-x: hidden;
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.65;
    }}
    main {{
      width: min(1120px, calc(100% - 32px));
      margin: 0 auto;
      padding: 34px 0 56px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 24px;
      align-items: flex-start;
      margin-bottom: 18px;
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
    .subhead {{ max-width: 620px; margin-bottom: 0; color: var(--muted); }}
    .header-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      justify-content: flex-end;
      align-items: center;
    }}
    section + section {{ margin-top: 32px; }}
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
    .status-strip {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 0 0 28px;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.68);
    }}
    .status-chip {{
      display: inline-flex;
      gap: 8px;
      align-items: center;
      min-height: 32px;
      max-width: 100%;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #fff;
      padding: 5px 11px;
      font-size: 0.88rem;
    }}
    .status-chip span {{
      color: var(--muted);
      white-space: nowrap;
    }}
    .status-chip strong {{
      min-width: 0;
      color: var(--ink);
      overflow-wrap: anywhere;
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
    .focus-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }}
    .focus-card {{
      display: flex;
      flex-direction: column;
      gap: 12px;
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfa;
      padding: 16px;
    }}
    .focus-card h3 {{
      font-size: 1.04rem;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }}
    .item-category {{
      align-self: flex-start;
      margin-bottom: 0;
      border-radius: 999px;
      background: var(--accent-soft);
      padding: 4px 10px;
      color: var(--accent-strong);
      font-size: 0.82rem;
      font-weight: 700;
    }}
    .item-detail {{
      border-top: 1px solid var(--line);
      padding-top: 10px;
    }}
    .item-detail span {{
      display: block;
      margin-bottom: 3px;
      color: var(--muted);
      font-size: 0.78rem;
      font-weight: 700;
    }}
    .item-detail p {{
      margin-bottom: 0;
      font-size: 0.94rem;
      overflow-wrap: anywhere;
    }}
    .source-link,
    .source-note {{
      margin-top: auto;
      overflow-wrap: anywhere;
      font-size: 0.86rem;
    }}
    .recent-list {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }}
    .recent-card {{
      display: flex;
      flex-direction: column;
      gap: 10px;
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 14px;
    }}
    .recent-card h3 {{ font-size: 1rem; }}
    .recent-body ol {{ margin-top: 0; }}
    .recent-meta {{
      margin: auto 0 0;
      color: var(--muted);
      font-size: 0.86rem;
    }}
    .compact-counts {{ gap: 6px; }}
    .compact-counts .count-pill {{
      min-height: 24px;
      padding: 3px 8px;
      font-size: 0.78rem;
    }}
    .fallback-list {{
      border-top: 1px solid var(--line);
      padding-top: 16px;
    }}
    .fallback-list h3 {{
      margin-bottom: 8px;
      color: var(--accent-strong);
      font-size: 0.95rem;
    }}
    .archive-month {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      overflow: hidden;
    }}
    .archive-month + .archive-month {{ margin-top: 10px; }}
    .archive-month summary {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      cursor: pointer;
      padding: 12px 14px;
      color: var(--accent-strong);
      font-weight: 700;
    }}
    .archive-month summary span + span {{
      color: var(--muted);
      font-size: 0.88rem;
      font-weight: 500;
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
    .secondary-link,
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
      white-space: nowrap;
    }}
    .primary-link {{
      border-color: var(--accent);
      background: var(--accent);
      color: #fff;
      font-weight: 700;
    }}
    .secondary-link {{
      color: var(--accent-strong);
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
      max-width: 100%;
      border-radius: 999px;
      background: var(--accent-soft);
      padding: 4px 10px;
      font-size: 0.88rem;
    }}
    .count-pill span {{ overflow-wrap: anywhere; }}
    .count-pill strong {{ color: var(--accent-strong); }}
    ol {{
      margin: 0;
      padding-left: 1.3rem;
    }}
    li {{
      overflow-wrap: anywhere;
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
      border-top: 1px solid var(--line);
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
    @media (max-width: 760px) {{
      main {{
        width: min(100% - 20px, 1120px);
        padding-top: 24px;
      }}
      header {{
        display: grid;
        gap: 14px;
        align-items: start;
      }}
      .header-actions {{
        justify-content: stretch;
        width: 100%;
      }}
      .header-actions a {{ flex: 1 1 11rem; }}
      .status-strip {{ margin-bottom: 24px; }}
      .status-chip {{
        min-height: 34px;
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
      .focus-grid {{
        grid-template-columns: 1fr;
        gap: 12px;
      }}
      .section-head {{
        display: grid;
        gap: 2px;
      }}
      .recent-list {{
        display: flex;
        gap: 10px;
        margin-inline: -10px;
        overflow-x: auto;
        padding: 0 10px 6px;
        scroll-snap-type: x proximity;
      }}
      .recent-card {{
        flex: 0 0 min(18rem, calc(100vw - 48px));
        scroll-snap-align: start;
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
        <p class="subhead">生活に関わるマレーシアニュースをRSSから日次で収集・要約しています。</p>
      </div>
      <div class="header-actions">
        <a class="primary-link" href="{primary_href}">今日の全文</a>
        <a class="secondary-link" href="#archive-heading">過去分を見る</a>
      </div>
    </header>
    {status_chips}

    <section aria-labelledby="today-heading">
      <div class="section-head">
        <h2 id="today-heading">今日見るべき3件</h2>
        <p>速報、生活インパクト、知っておくと得の順に表示</p>
      </div>
      {latest_summary}
    </section>

    <section aria-labelledby="recent-heading">
      <div class="section-head">
        <h2 id="recent-heading">直近7日の流れ</h2>
        <p>今日を除く直近日を比較</p>
      </div>
      <div class="recent-list">
        {recent_rows}
      </div>
    </section>

    <section aria-labelledby="archive-heading">
      <div class="section-head">
        <h2 id="archive-heading">月別アーカイブ</h2>
        <p>過去分を見る</p>
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
    rendered = "\n".join(line.rstrip() for line in render_html(days).splitlines()) + "\n"
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    print(f"Wrote index: {OUTPUT_PATH}")
    print(f"Indexed days: {len(days)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

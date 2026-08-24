from __future__ import annotations
#!/usr/bin/env python3
import html
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from malaysia_news_design_tokens import MALAYSIA_NEWS_TOKENS_CSS


MYT = timezone(timedelta(hours=8))
NEWS_DIR = Path("news/malaysia")
OUTPUT_PATH = NEWS_DIR / "index.html"
CATEGORIES = ("【速報】", "【生活インパクト】", "【知っておくと得】")
PICKUP_HEADLINE_MAX_WIDTH = 15.5


@dataclass
class NewsItem:
    category: str
    conclusion: str = ""
    short_headline: str = ""
    summary_points: list[str] = field(default_factory=list)
    what_happened: str = ""
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
        "- 短見出し：": "short_headline",
        "- 補足：": "summary_points",
        "- 何が起きた：": "what_happened",
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

        if line.startswith("- 概要：") or line.startswith("- 結論："):
            flush_item()
            prefix = "- 概要：" if line.startswith("- 概要：") else "- 結論："
            conclusion = line[len(prefix) :].strip()
            if current_category in category_counts:
                category_counts[current_category] += 1
            conclusions.append(conclusion)
            if current_category in CATEGORIES:
                current_item = NewsItem(category=current_category, conclusion=conclusion)
            continue

        if current_item:
            for prefix, field_name in optional_labels.items():
                if line.startswith(prefix):
                    value = line[len(prefix) :].strip()
                    if field_name == "summary_points":
                        current_item.summary_points.append(value)
                        break
                    previous = getattr(current_item, field_name)
                    setattr(current_item, field_name, f"{previous} {value}".strip())
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


def headline_width(text: str) -> float:
    return sum(0.5 if ord(character) < 128 else 1.0 for character in text)


def take_headline_width(text: str, max_width: float) -> str:
    result: list[str] = []
    used = 0.0
    for character in text:
        character_width = 0.5 if ord(character) < 128 else 1.0
        if used + character_width > max_width:
            break
        result.append(character)
        used += character_width
    return "".join(result).rstrip("、，,・:： ")


def semantic_headline(text: str) -> str:
    """Turn the long editorial summary into a compact, topic-preserving label."""
    normalized = " ".join(text.split())
    if ("呼吸器" in normalized or ("喘息" in normalized and "上気道感染" in normalized)) and "急増" in normalized:
        return "煙害で呼吸器疾患が急増"
    if "2027年度予算" in normalized and "生活費" in normalized:
        return "27年度予算 生活費対策重視"
    if ("倒壊リスク" in normalized or "老朽化した木" in normalized) and "センサー" in normalized:
        return "KL市 倒木監視にセンサー"
    if "ECOSS" in normalized and "苦情" in normalized and "減少" in normalized:
        return "ECOSSで油隠し苦情減"
    if "テレンガヌ" in normalized and "市場" in normalized and "遵守" in normalized:
        return "テレンガヌ 5市場が遵守認定"
    if "留学生" in normalized and "経済効果" in normalized:
        return "留学生が経済効果2百億RM"

    first_sentence = re.split(r"[。.!！?？]", normalized, maxsplit=1)[0]
    first_sentence = re.sub(r"（[^）]*）", "", first_sentence)
    first_sentence = re.sub(r"^.+?は、", "", first_sentence)
    first_sentence = re.sub(r"と(?:発表|説明|述べ)しました?$", "", first_sentence)
    return first_sentence.strip()


def shorten_pickup_headline(text: str, limit: float = PICKUP_HEADLINE_MAX_WIDTH) -> str:
    compact = semantic_headline(text)
    if headline_width(compact) <= limit:
        return compact
    truncated = take_headline_width(compact, limit - 1.0)
    return f"{truncated}…"


def item_summary_body(item: NewsItem) -> str:
    parts = [item.conclusion, *item.summary_points, item.what_happened, item.life_impact, item.next_action]
    unique_parts: list[str] = []
    for part in parts:
        normalized = part.strip()
        if normalized and normalized not in unique_parts:
            unique_parts.append(normalized)
    return " ".join(unique_parts)


def markdown_link(day: NewsDay) -> str:
    return f"./{esc(day.path.name)}"


def daily_page_link(day: NewsDay) -> str:
    return f"./{esc(day.date)}.html"


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
      <a class="markdown-link" href="{markdown_link(day)}">Markdown版</a>
    </div>
    """


def render_item_card(item: NewsItem) -> str:
    display_headline = shorten_pickup_headline(item.conclusion)
    source = ""
    if item.source_url:
        source_label = item.source or "出典"
        source = f'<a class="source-link" href="{esc(item.source_url)}">出典: {esc(source_label)}</a>'
    elif item.source:
        source = f'<span class="source-note">出典: {esc(item.source)}</span>'

    return f"""
        <article class="focus-card">
          <p class="item-category">{esc(category_label(item.category))}</p>
          <h3 title="{esc(item.conclusion)}">{esc(display_headline)}</h3>
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
            <p class="muted">カテゴリ順に、生活への影響を確認できます。</p>
          </div>
          <a class="primary-link" href="{daily_page_link(day)}">10件すべて読む</a>
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
          <a class="open-link" href="{daily_page_link(day)}">その日のまとめ</a>
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
              <a href="{daily_page_link(day)}">{esc(format_date(day.date))}</a>
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


def render_daily_item(item: NewsItem, position: int) -> str:
    if item.source_url:
        source_label = item.source or "出典を開く"
        source = f'<a class="source-link" href="{esc(item.source_url)}">出典: {esc(source_label)}</a>'
    elif item.source:
        source = f'<p class="source-note">出典: {esc(item.source)}</p>'
    else:
        source = ""

    return f"""
      <article class="daily-item">
        <div class="daily-item-head">
          <span class="item-number">{position}</span>
          <p class="item-category">{esc(category_label(item.category))}</p>
        </div>
        <h3>{esc(shorten_pickup_headline(item.short_headline or item.conclusion))}</h3>
        <p class="daily-summary">{esc(item_summary_body(item))}</p>
        {source}
      </article>
    """


def render_daily_sections(day: NewsDay) -> str:
    sections = []
    position = 0
    for category in CATEGORIES:
        category_items = [item for item in ordered_items(day) if item.category == category]
        if category_items:
            cards = []
            for item in category_items:
                position += 1
                cards.append(render_daily_item(item, position))
            content = "\n".join(cards)
        else:
            content = '<p class="muted">このカテゴリの掲載はありません。</p>'
        category_id = f"category-{CATEGORIES.index(category) + 1}"
        sections.append(
            f"""
            <section class="daily-category" aria-labelledby="{category_id}">
              <div class="daily-category-head">
                <h2 id="{category_id}">{esc(category_label(category))}</h2>
                <span>{day.category_counts.get(category, 0)}件</span>
              </div>
              <div class="daily-item-list">
                {content}
              </div>
            </section>
            """
        )
    return "\n".join(sections)


def render_daily_page(day: NewsDay) -> str:
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(format_date(day.date))}のニュースまとめ | マレーシア生活ニュース</title>
  <style>
{MALAYSIA_NEWS_TOKENS_CSS}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: var(--font-sans);
      line-height: 1.7;
    }}
    main {{ width: min(880px, calc(100% - 32px)); margin: 0 auto; padding: 28px 0 56px; }}
    h1, h2, h3, p {{ margin-top: 0; }}
    h1 {{ margin-bottom: 8px; font-size: clamp(2rem, 6vw, 3.1rem); line-height: 1.16; }}
    h2 {{ margin: 0; font-size: 1.25rem; }}
    h3 {{ margin: 0; font-size: 1.1rem; line-height: 1.55; overflow-wrap: anywhere; }}
    a {{ color: var(--accent); text-underline-offset: 0.18em; }}
    a:focus-visible {{ outline: 3px solid var(--focus); outline-offset: 3px; border-radius: var(--radius-control); }}
    .page-header {{ margin-bottom: 28px; }}
    .page-nav {{ display: flex; justify-content: space-between; gap: 16px; align-items: center; margin-bottom: 28px; }}
    .back-link {{ font-weight: 700; }}
    .markdown-link {{ color: var(--muted); font-size: .9rem; }}
    .eyebrow {{ margin-bottom: 3px; color: var(--accent); font-size: .78rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }}
    .subhead {{ max-width: 650px; margin-bottom: 0; color: var(--muted); }}
    .summary-strip {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }}
    .count-pill {{ display: inline-flex; gap: 8px; align-items: center; min-height: 30px; border-radius: var(--radius-pill); background: var(--accent-soft); padding: 4px 10px; font-size: .88rem; }}
    .count-pill strong {{ color: var(--accent-strong); }}
    .category-nav {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 24px; }}
    .category-nav a {{ border: 1px solid var(--line); border-radius: var(--radius-pill); background: var(--panel); padding: 6px 11px; color: var(--accent-strong); font-size: .9rem; font-weight: 700; text-decoration: none; }}
    .daily-category + .daily-category {{ margin-top: 32px; }}
    .daily-category-head {{ display: flex; justify-content: space-between; gap: 12px; align-items: baseline; border-bottom: 2px solid var(--accent-soft); padding-bottom: 9px; }}
    .daily-category-head span {{ color: var(--muted); font-size: .9rem; }}
    .daily-item-list {{ display: grid; gap: 12px; margin-top: 12px; }}
    .daily-item {{ border: 1px solid var(--line); border-radius: var(--radius-card); background: var(--panel); padding: 18px; box-shadow: var(--shadow); }}
    .daily-item-head {{ display: flex; gap: 8px; align-items: center; margin-bottom: 10px; }}
    .item-number {{ display: inline-grid; width: 1.6rem; height: 1.6rem; place-items: center; border-radius: 50%; background: var(--accent-soft); color: var(--accent-strong); font-size: .8rem; font-weight: 700; }}
    .item-category {{ margin: 0; color: var(--accent-strong); font-size: .85rem; font-weight: 700; }}
    .daily-summary {{ margin: 16px 0 0; overflow-wrap: anywhere; }}
    .source-link, .source-note {{ display: block; margin: 16px 0 0; font-size: .88rem; overflow-wrap: anywhere; }}
    .source-note {{ color: var(--muted); }}
    .muted {{ color: var(--muted); }}
    @media (max-width: 600px) {{
      main {{ width: min(100% - 20px, 880px); padding-top: 20px; }}
      .page-nav {{ align-items: flex-start; flex-direction: column; gap: 6px; margin-bottom: 24px; }}
      .daily-item {{ padding: 15px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header class="page-header">
      <nav class="page-nav" aria-label="ページ内ナビゲーション">
        <a class="back-link" href="./index.html">← マレーシア生活ニュース</a>
        <a class="markdown-link" href="{markdown_link(day)}">Markdown版</a>
      </nav>
      <p class="eyebrow">Daily summary</p>
      <h1>{esc(format_date(day.date))}のニュースまとめ</h1>
      <p class="subhead">RSSから収集・要約したニュースを、生活への影響と次の行動が分かる形でまとめています。</p>
      <div class="summary-strip" aria-label="カテゴリ別件数">
        {render_counts(day)}
      </div>
    </header>
    <nav class="category-nav" aria-label="カテゴリへ移動">
      {''.join(f'<a href="#category-{index + 1}">{esc(category_label(category))} {day.category_counts.get(category, 0)}件</a>' for index, category in enumerate(CATEGORIES))}
    </nav>
    {render_daily_sections(day)}
  </main>
</body>
</html>
"""


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
        primary_href = daily_page_link(latest)
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
  <title>マレーシア生活ニュース</title>
  <style>
{MALAYSIA_NEWS_TOKENS_CSS}
    * {{ box-sizing: border-box; }}
    html {{ overflow-x: hidden; }}
    body {{
      margin: 0;
      overflow-x: hidden;
      background: var(--bg);
      color: var(--ink);
      font-family: var(--font-sans);
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
      font-size: clamp(1.75rem, 3vw, 2.625rem);
      line-height: 1.08;
      letter-spacing: 0;
    }}
    h2 {{
      margin-bottom: 0;
      font-size: clamp(1.4rem, 2.4vw, 1.875rem);
      line-height: 1.16;
    }}
    h3 {{ margin: 0; font-size: 1rem; line-height: 1.35; }}
    a {{
      color: var(--accent);
      text-decoration-thickness: 0.08em;
      text-underline-offset: 0.18em;
    }}
    a:focus-visible {{
      outline: 3px solid var(--focus);
      outline-offset: 3px;
      border-radius: var(--radius-control);
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
      border-radius: var(--radius-card);
      background: var(--panel-translucent);
    }}
    .status-chip {{
      display: inline-flex;
      gap: 8px;
      align-items: center;
      min-height: 32px;
      max-width: 100%;
      border: 1px solid var(--line);
      border-radius: var(--radius-pill);
      background: var(--panel);
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
      border-radius: var(--radius-card);
      background: var(--panel-subtle);
      padding: 16px;
    }}
    .focus-card h3 {{
      font-size: 1.04rem;
      line-height: 1.45;
      overflow-wrap: anywhere;
      display: -webkit-box;
      overflow: hidden;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 3;
    }}
    .item-category {{
      align-self: flex-start;
      margin-bottom: 0;
      border-radius: var(--radius-pill);
      background: var(--accent-soft);
      padding: 4px 10px;
      color: var(--accent-strong);
      font-size: 0.82rem;
      font-weight: 700;
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
      border-radius: var(--radius-card);
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
      border-radius: var(--radius-pill);
      padding: 7px 13px;
      background: var(--panel);
      font-size: 0.9rem;
      line-height: 1.2;
      text-decoration: none;
      white-space: nowrap;
    }}
    .primary-link {{
      border-color: var(--accent);
      background: var(--accent);
      color: var(--panel);
      font-weight: 700;
    }}
    .secondary-link {{
      color: var(--accent-strong);
      font-weight: 700;
    }}
    .markdown-link {{
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 4px 8px;
      color: var(--muted);
      font-size: 0.86rem;
      white-space: nowrap;
    }}
    .status-strip .markdown-link {{ margin-left: auto; }}
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
      border-radius: var(--radius-pill);
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
      .status-strip .markdown-link {{ margin-left: 0; }}
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
        <h1>マレーシア生活ニュース</h1>
        <p class="subhead">生活に関わるマレーシアニュースをRSSから日次で収集・要約しています。</p>
      </div>
      <div class="header-actions">
        <a class="primary-link" href="{primary_href}">今日のまとめを読む</a>
        <a class="secondary-link" href="#archive-heading">過去分を見る</a>
      </div>
    </header>
    {status_chips}

    <section aria-labelledby="today-heading">
      <div class="section-head">
        <h2 id="today-heading">今日のピックアップ3件</h2>
        <p>速報、生活インパクト、知っておくと得の順に表示</p>
      </div>
      {latest_summary}
    </section>

    <section aria-labelledby="recent-heading">
      <div class="section-head">
        <h2 id="recent-heading">直近7日のまとめ</h2>
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
    for day in days:
        daily_output = NEWS_DIR / f"{day.date}.html"
        daily_rendered = "\n".join(
            line.rstrip() for line in render_daily_page(day).splitlines()
        ) + "\n"
        daily_output.write_text(daily_rendered, encoding="utf-8")
    print(f"Wrote index: {OUTPUT_PATH}")
    print(f"Wrote daily pages: {len(days)}")
    print(f"Indexed days: {len(days)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

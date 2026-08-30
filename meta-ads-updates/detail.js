(async function renderMetaAdsFeedDetail() {
  "use strict";

  const params = new URLSearchParams(window.location.search);
  const itemId = params.get("id");
  const elements = {
    back: document.querySelector("#back-link"),
    notice: document.querySelector("#detail-unofficial-notice"),
    card: document.querySelector("#detail-card"),
    heading: document.querySelector("#detail-heading"),
    title: document.querySelector("#detail-title"),
    summary: document.querySelector("#detail-summary"),
    originalTitle: document.querySelector("#detail-original-title"),
    facts: document.querySelector("#detail-facts"),
    sourceLink: document.querySelector("#detail-source-link"),
    error: document.querySelector("#detail-error"),
    errorTitle: document.querySelector("#detail-error-title"),
    errorCopy: document.querySelector("#detail-error-copy")
  };

  function element(tagName, className, text) {
    const node = document.createElement(tagName);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function personalHeadline(item) {
    return item.presentation?.status === "generated" && item.presentation.shortHeadlineJa
      ? item.presentation.shortHeadlineJa
      : item.title;
  }

  function appendFact(grid, label, value, fallback = "確認できず") {
    const wrapper = element("div");
    wrapper.append(element("dt", "fact-label", label), element("dd", value ? "" : "not-stated", value || fallback));
    grid.append(wrapper);
  }

  function safeHttpsUrl(value) {
    try {
      const parsed = new URL(value);
      return parsed.protocol === "https:" ? parsed.href : null;
    } catch {
      return null;
    }
  }

  function setBackLink() {
    const back = new URL("./index.html", window.location.href);
    for (const name of ["source", "type", "q", "personal-fixture"]) {
      const value = params.get(name);
      if (value) back.searchParams.set(name, value.slice(0, 160));
    }
    elements.back.href = `${back.pathname}${back.search}`;
  }

  function showError(title, copy) {
    elements.card.hidden = true;
    elements.notice.hidden = true;
    elements.errorTitle.textContent = title;
    elements.errorCopy.textContent = copy;
    elements.error.hidden = false;
  }

  setBackLink();
  if (!itemId || itemId.length > 160) {
    showError("記事を特定できません", "一覧へ戻り、もう一度記事を選択してください。");
    return;
  }

  try {
    const response = await fetch("./personal-feed.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`report HTTP ${response.status}`);
    const report = await response.json();
    if (report.schemaVersion !== "meta-ads-personal-feed/v1" && report.schemaVersion !== "meta-ads-personal-feed/v2") {
      throw new Error("unsupported report");
    }
    const item = Array.isArray(report.items) ? report.items.find((candidate) => candidate.id === itemId) : null;
    const source = item && Array.isArray(report.sources) ? report.sources.find((candidate) => candidate.id === item.sourceId) : null;
    const sourceUrl = item ? safeHttpsUrl(item.url) : null;
    if (!item || !source || !sourceUrl) {
      showError("記事が見つかりません", "この記事は更新または保存期間の終了により、一覧から削除された可能性があります。");
      return;
    }

    const isOfficial = source.classification === "official";
    const badge = element("span", isOfficial ? "origin-label origin-label--official" : "origin-label origin-label--unofficial", isOfficial ? "Meta公式" : "非公式・未確認");
    elements.heading.append(badge, element("p", "source-name", source.name));
    elements.title.textContent = personalHeadline(item);
    elements.summary.textContent = item.presentation?.status === "generated" && item.presentation.summaryJa
      ? item.presentation.summaryJa
      : "日本語要約を準備中です。原文タイトルと元の記事をご確認ください。";
    elements.originalTitle.textContent = item.title;
    appendFact(elements.facts, "発表日", item.publishedDate);
    appendFact(elements.facts, "最終更新日", item.updatedDate);
    appendFact(elements.facts, "対象", Array.isArray(item.platforms) ? item.platforms.join(" / ") : null, "未分類");
    appendFact(elements.facts, "最終確認", typeof item.lastObservedAt === "string" ? item.lastObservedAt.slice(0, 10) : null);
    elements.sourceLink.href = sourceUrl;
    elements.sourceLink.textContent = isOfficial ? "公式ソースを開く" : "非公式ソースを開く";
    elements.notice.hidden = isOfficial;
    elements.card.hidden = false;
    document.title = `${personalHeadline(item)} | Meta Ads Update Feed`;
  } catch (error) {
    showError("現在の公開内容を表示できません", "公開フィードを読み込めませんでした。しばらくしてからもう一度お試しください。");
    console.error(error);
  }
})();

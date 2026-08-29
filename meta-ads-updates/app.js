(async function renderMetaAdsFeed() {
  "use strict";

  const demoMode = new URLSearchParams(window.location.search).get("demo") === "1";
  const fixtureMode = new URLSearchParams(window.location.search).has("fixture");
  const reportPath = demoMode ? "./demo-latest.json" : fixtureMode ? "./latest.json" : "./personal-feed.json";
  const sourceNames = {
    "meta-product-news-rss": "Product News",
    "meta-business-sdk-releases": "Business SDK Releases",
    "ppc-land-meta-ads": "PPC Land",
    "jon-loomer-meta-ads": "Jon Loomer Digital"
  };
  const changeTypeLabels = { new_url: "新規記事", content_changed: "本文更新", sdk_release: "SDK release" };
  const priorityLabels = { high: "高優先度", standard: "標準", low: "低優先度" };
  const actionLabels = { action_required: "対応が必要", review_required: "確認が必要", not_required: "現時点の対応不要" };
  const elements = {
    demoBanner: document.querySelector("#demo-banner"),
    recoveryBanner: document.querySelector("#recovery-banner"),
    recoveryBannerCopy: document.querySelector("#recovery-banner-copy"),
    unofficialNotice: document.querySelector("#unofficial-notice"),
    week: document.querySelector("#week-stamp"),
    form: document.querySelector("#filter-form"),
    source: document.querySelector("#source-filter"),
    priority: document.querySelector("#priority-filter"),
    priorityLabel: document.querySelector("#priority-filter-label"),
    query: document.querySelector("#query-filter"),
    reset: document.querySelector("#reset-button"),
    summary: document.querySelector("#result-summary"),
    list: document.querySelector("#update-list"),
    empty: document.querySelector("#empty-state"),
    emptyTitle: document.querySelector("#empty-title"),
    emptyCopy: document.querySelector("#empty-copy"),
    footer: document.querySelector("#tracker-footer")
  };

  function element(tagName, className, text) {
    const node = document.createElement(tagName);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function appendFact(grid, label, value, fallback = "公式発表に記載なし") {
    const wrapper = element("div");
    wrapper.append(element("dt", "fact-label", label), element("dd", value ? "" : "not-stated", value || fallback));
    grid.append(wrapper);
  }

  function appendAssessment(grid, label, assessment, isAction) {
    const panel = element("section", "assessment");
    const summary = assessment.status === "not_stated" ? "公式発表に記載なし" : assessment.summary;
    const detail = element("p", isAction && assessment.status === "action_required" ? "action-required" : assessment.status === "not_stated" ? "not-stated" : "", isAction && assessment.status !== "not_stated" ? `${actionLabels[assessment.status]}：${summary}` : summary);
    panel.append(element("p", "assessment-label", label), detail);
    if (assessment.assessmentSource === "human_review") panel.append(element("span", "human-review-label", "人間レビュー済み評価"));
    grid.append(panel);
  }

  function renderReviewedItem(item) {
    const listItem = document.createElement("li");
    const card = element("article", `update-card${item.priority === "high" ? " update-card--high" : ""}`);
    const heading = element("div", "card-heading");
    heading.append(element("span", "change-kind", changeTypeLabels[item.changeType]), element("span", `priority-label priority-label--${item.priority}`, priorityLabels[item.priority]), element("p", "source-name", sourceNames[item.sourceId] || item.sourceId));
    const facts = element("dl", "fact-grid");
    appendFact(facts, "発表日", item.announcementDate.status === "stated" ? item.announcementDate.value : null);
    appendFact(facts, "適用日", item.effectiveDate.status === "stated" ? item.effectiveDate.value : null);
    appendFact(facts, "rollout", item.rollout.status === "stated" ? item.rollout.value : null);
    appendFact(facts, "対象", item.targets.status === "stated" ? item.targets.value : null);
    const assessments = element("div", "assessment-grid");
    appendAssessment(assessments, "実務影響", item.businessImpact, false);
    appendAssessment(assessments, "対応要否", item.action, true);
    const sourceLink = element("a", "source-link", demoMode ? "公式ソース例を開く" : "公式URLを開く");
    sourceLink.href = item.officialUrl;
    sourceLink.target = "_blank";
    sourceLink.rel = "noreferrer";
    card.append(heading, element("h2", "", item.title), facts, assessments, sourceLink);
    listItem.append(card);
    return listItem;
  }

  function renderPersonalItem(item, source) {
    const listItem = document.createElement("li");
    const card = element("article", `update-card update-card--${source.classification}`);
    const heading = element("div", "card-heading");
    const badge = source.classification === "official"
      ? element("span", "origin-label origin-label--official", "Meta公式")
      : element("span", "origin-label origin-label--unofficial", "非公式・未確認");
    heading.append(badge, element("p", "source-name", source.name));
    const facts = element("dl", "fact-grid");
    appendFact(facts, "発表日", item.publishedDate);
    appendFact(facts, "最新更新日", item.updatedDate, "確認できず");
    appendFact(facts, "対象", item.platforms.join(" / "), "未分類");
    appendFact(facts, "最終確認", item.lastObservedAt.slice(0, 10), "確認できず");
    card.append(heading, element("h2", "", item.title), facts);
    if (source.classification === "unofficial") card.append(element("p", "unofficial-copy", "この情報は非公式ソースです。対応や判断の前に、必ずMeta公式情報を確認してください。"));
    const sourceLink = element("a", "source-link", source.classification === "official" ? "公式ソースを開く" : "非公式ソースを開く");
    sourceLink.href = item.url;
    sourceLink.target = "_blank";
    sourceLink.rel = "noreferrer";
    card.append(sourceLink);
    listItem.append(card);
    return listItem;
  }

  function setOptions(select, options, selected) {
    select.replaceChildren(...options.map(({ value, label }) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      if (value === selected) option.selected = true;
      return option;
    }));
  }

  try {
    const response = await fetch(reportPath, { cache: "no-store" });
    if (!response.ok) throw new Error(`report HTTP ${response.status}`);
    const report = await response.json();
    const personalMode = report.schemaVersion === "meta-ads-personal-feed/v1";
    const sourceMap = new Map((report.sources || []).map((source) => [source.id, source]));
    const delayedRecovery = !personalMode && report.publication?.mode === "delayed_recovery";
    elements.demoBanner.hidden = !demoMode;
    elements.recoveryBanner.hidden = !delayedRecovery;
    elements.unofficialNotice.hidden = !personalMode;
    if (demoMode) elements.footer.textContent = "この画面は架空データによるデモです。実運用の承認・判断には使用しないでください。";
    if (delayedRecovery) {
      const missingDates = Array.isArray(report.publication.missingPreCutoffDates) ? report.publication.missingPreCutoffDates.join("、") : "不明";
      elements.recoveryBannerCopy.textContent = `金曜17:00 MYTの締切前candidateが不足したため、人間確認済みの回復データを表示しています。不足日: ${missingDates}。`;
    }
    if (personalMode) {
      elements.week.textContent = report.generatedAt ? `最終取得: ${report.generatedAt.replace("T", " ").replace("Z", " UTC")}` : "初回取得待ち";
      elements.priorityLabel.textContent = "ソース区分";
      elements.footer.textContent = "個人・同僚向けの自動情報フィードです。Meta公式と非公式情報を区別して表示します。非公式情報は判断・対応の根拠にせず、必ず公式情報を確認してください。";
      setOptions(elements.source, [{ value: "all", label: "すべてのソース" }, ...report.sources.map((source) => ({ value: source.id, label: source.name }))], "all");
      setOptions(elements.priority, [{ value: "all", label: "すべて" }, { value: "official", label: "Meta公式" }, { value: "unofficial", label: "非公式・未確認" }], "all");
    } else {
      elements.week.textContent = report.week.label;
      elements.priorityLabel.textContent = "優先度";
      setOptions(elements.source, [{ value: "all", label: "すべてのソース" }, { value: "meta-product-news-rss", label: "Product News" }, { value: "meta-business-sdk-releases", label: "Business SDK Releases" }], "all");
      setOptions(elements.priority, [{ value: "all", label: "すべて" }, { value: "high", label: "高" }, { value: "standard", label: "標準" }, { value: "low", label: "低" }], "all");
    }
    const state = { filters: { sourceId: "all", type: "all", query: "" } };

    function hasActiveFilter() {
      return state.filters.sourceId !== "all" || state.filters.type !== "all" || Boolean(state.filters.query.trim());
    }
    function visibleItems() {
      const query = state.filters.query.trim().toLocaleLowerCase("ja-JP");
      return report.items.filter((item) => {
        const source = sourceMap.get(item.sourceId);
        const type = personalMode ? source?.classification : item.priority;
        return (state.filters.sourceId === "all" || item.sourceId === state.filters.sourceId) && (state.filters.type === "all" || type === state.filters.type) && (!query || item.title.toLocaleLowerCase("ja-JP").includes(query));
      });
    }
    function render() {
      const items = visibleItems();
      elements.list.replaceChildren(...items.map((item) => personalMode ? renderPersonalItem(item, sourceMap.get(item.sourceId)) : renderReviewedItem(item)));
      elements.empty.hidden = items.length > 0;
      if (!items.length) {
        elements.emptyTitle.textContent = hasActiveFilter() ? "条件に一致する更新はありません" : personalMode ? "取得済みの情報はありません" : "この週の承認済み更新はありません";
        elements.emptyCopy.textContent = hasActiveFilter() ? "検索語または絞り込み条件を変更してください。" : personalMode ? "初回取得後にソースからの情報を表示します。" : "次回の公式更新を待機しています。取得やレビューに失敗しても、公開済み内容は変更しません。";
      }
      elements.summary.replaceChildren(document.createTextNode("表示中："), Object.assign(document.createElement("strong"), { textContent: `${items.length}件` }), document.createTextNode(demoMode ? "（デモ用の架空更新）" : personalMode ? "（自動取得・要確認）" : "（承認済みの公式更新）"));
    }
    function syncControls() {
      elements.source.value = state.filters.sourceId;
      elements.priority.value = state.filters.type;
      elements.query.value = state.filters.query;
    }
    elements.form.addEventListener("submit", (event) => event.preventDefault());
    elements.source.addEventListener("change", () => { state.filters.sourceId = elements.source.value; render(); });
    elements.priority.addEventListener("change", () => { state.filters.type = elements.priority.value; render(); });
    elements.query.addEventListener("input", () => { state.filters.query = elements.query.value; render(); });
    elements.reset.addEventListener("click", () => { state.filters = { sourceId: "all", type: "all", query: "" }; syncControls(); render(); });
    syncControls();
    render();
  } catch (error) {
    elements.week.textContent = "公開フィードを読み込めません";
    elements.emptyTitle.textContent = "現在の公開内容を表示できません";
    elements.emptyCopy.textContent = "取得に失敗したため、公開済み内容を変更していません。";
    elements.empty.hidden = false;
    console.error(error);
  }
})();

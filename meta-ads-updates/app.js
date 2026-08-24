(async function renderApprovedTracker() {
  "use strict";

  const sourceNames = {
    "meta-product-news-rss": "Product News",
    "meta-business-sdk-releases": "Business SDK Releases"
  };
  const changeTypeLabels = {
    new_url: "新規記事",
    content_changed: "本文更新",
    sdk_release: "SDK release"
  };
  const priorityLabels = {
    high: "高優先度",
    standard: "標準",
    low: "低優先度"
  };
  const actionLabels = {
    action_required: "対応が必要",
    review_required: "確認が必要",
    not_required: "現時点の対応不要"
  };
  const demoMode = new URLSearchParams(window.location.search).get("demo") === "1";
  const reportPath = demoMode ? "./demo-latest.json" : "./latest.json";
  const elements = {
    demoBanner: document.querySelector("#demo-banner"),
    week: document.querySelector("#week-stamp"),
    form: document.querySelector("#filter-form"),
    source: document.querySelector("#source-filter"),
    priority: document.querySelector("#priority-filter"),
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

  function factValue(fact) {
    return fact.status === "stated" ? fact.value : "公式発表に記載なし";
  }

  function appendFact(grid, label, fact) {
    const wrapper = element("div");
    wrapper.append(
      element("dt", "fact-label", label),
      element("dd", fact.status === "stated" ? "" : "not-stated", factValue(fact))
    );
    grid.append(wrapper);
  }

  function appendAssessment(grid, label, assessment, isAction) {
    const panel = element("section", "assessment");
    const summary = assessment.status === "not_stated" ? "公式発表に記載なし" : assessment.summary;
    const detail = element(
      "p",
      isAction && assessment.status === "action_required" ? "action-required" : assessment.status === "not_stated" ? "not-stated" : "",
      isAction && assessment.status !== "not_stated" ? `${actionLabels[assessment.status]}：${summary}` : summary
    );
    panel.append(element("p", "assessment-label", label), detail);
    if (assessment.assessmentSource === "human_review") {
      panel.append(element("span", "human-review-label", "人間レビュー済み評価"));
    }
    grid.append(panel);
  }

  function renderItem(item) {
    const listItem = document.createElement("li");
    const card = element("article", `update-card${item.priority === "high" ? " update-card--high" : ""}`);
    const heading = element("div", "card-heading");
    heading.append(
      element("span", "change-kind", changeTypeLabels[item.changeType]),
      element("span", `priority-label priority-label--${item.priority}`, priorityLabels[item.priority]),
      element("p", "source-name", sourceNames[item.sourceId] || item.sourceId)
    );
    const facts = element("dl", "fact-grid");
    appendFact(facts, "発表日", item.announcementDate);
    appendFact(facts, "適用日", item.effectiveDate);
    appendFact(facts, "rollout", item.rollout);
    appendFact(facts, "対象", item.targets);
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

  try {
    elements.demoBanner.hidden = !demoMode;
    if (demoMode) {
      elements.footer.textContent = "この画面は架空データによるデモです。実運用の承認・判断には使用しないでください。";
    }
    const response = await fetch(reportPath, { cache: "no-store" });
    if (!response.ok) throw new Error(`report HTTP ${response.status}`);
    const report = await response.json();
    const state = { filters: { sourceId: "all", priority: "all", query: "" } };

    function hasActiveFilter() {
      return state.filters.sourceId !== "all" || state.filters.priority !== "all" || Boolean(state.filters.query.trim());
    }

    function visibleItems() {
      const query = state.filters.query.trim().toLocaleLowerCase("ja-JP");
      return report.items.filter((item) =>
        (state.filters.sourceId === "all" || item.sourceId === state.filters.sourceId) &&
        (state.filters.priority === "all" || item.priority === state.filters.priority) &&
        (!query || item.title.toLocaleLowerCase("ja-JP").includes(query))
      );
    }

    function render() {
      const items = visibleItems();
      elements.list.replaceChildren(...items.map(renderItem));
      elements.empty.hidden = items.length > 0;
      if (!items.length) {
        const filtered = hasActiveFilter();
        elements.emptyTitle.textContent = filtered ? "条件に一致する更新はありません" : "この週の承認済み更新はありません";
        elements.emptyCopy.textContent = filtered
          ? "検索語または絞り込み条件を変更してください。"
          : "次回の公式更新を待機しています。取得やレビューに失敗しても、公開済み内容は変更しません。";
      }
      elements.summary.replaceChildren(
        document.createTextNode("表示中："),
        Object.assign(document.createElement("strong"), { textContent: `${items.length}件` }),
        document.createTextNode(demoMode ? "（デモ用の架空更新）" : "（承認済みの公式更新）")
      );
    }

    function syncControls() {
      elements.source.value = state.filters.sourceId;
      elements.priority.value = state.filters.priority;
      elements.query.value = state.filters.query;
    }

    elements.week.textContent = report.week.label;
    elements.form.addEventListener("submit", (event) => event.preventDefault());
    elements.source.addEventListener("change", () => { state.filters.sourceId = elements.source.value; render(); });
    elements.priority.addEventListener("change", () => { state.filters.priority = elements.priority.value; render(); });
    elements.query.addEventListener("input", () => { state.filters.query = elements.query.value; render(); });
    elements.reset.addEventListener("click", () => {
      state.filters = { sourceId: "all", priority: "all", query: "" };
      syncControls();
      render();
    });
    syncControls();
    render();
  } catch (error) {
    elements.week.textContent = "公開レポートを読み込めません";
    elements.emptyTitle.textContent = "現在の公開内容を表示できません";
    elements.emptyCopy.textContent = "取得に失敗したため、公開済み内容を変更していません。";
    elements.empty.hidden = false;
    console.error(error);
  }
})();

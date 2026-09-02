(async function localizedMetaAdsFeed() {
  "use strict";

  const params = new URLSearchParams(window.location.search);
  const locale = document.documentElement.lang === "ja" ? "ja" : "en";
  const demoMode = params.get("demo") === "1";
  const fixtureMode = params.has("fixture");
  const root = locale === "ja" ? "../" : "./";
  const personalVersions = new Set(["meta-ads-personal-feed/v1", "meta-ads-personal-feed/v2", "meta-ads-personal-feed/v3"]);
  const words = locale === "ja" ? {
    allSources: "すべてのソース", allTypes: "すべて", official: "Meta公式", unofficial: "非公式・未確認",
    retrieved: "最終取得", waiting: "初回取得待ち", shown: "表示中：", automatic: "件（自動取得・要確認）",
    published: "発表日", updated: "最終更新日", unknown: "確認できず", details: "詳細を見る",
    noMatches: "条件に一致する更新はありません", noMatchesCopy: "検索語または絞り込み条件を変更してください。",
    noItems: "取得済みの情報はありません", noItemsCopy: "初回取得後にソースからの情報を表示します。",
    error: "公開フィードを読み込めません", errorTitle: "現在の公開内容を表示できません", errorCopy: "公開フィードを読み込めませんでした。しばらくしてからもう一度お試しください。",
    demoFooter: "この画面は架空データによるデモです。実運用の承認・判断には使用しないでください。", demoResult: "（デモ用の架空更新）", demoLink: "公式ソース例を開く"
  } : {
    allSources: "All sources", allTypes: "All", official: "Official", unofficial: "Unofficial",
    retrieved: "Last retrieved", waiting: "Waiting for first retrieval", shown: "Showing ", automatic: " items · automatically collected, verify before use",
    published: "Published", updated: "Updated", unknown: "Not found", details: "View details",
    noMatches: "No updates match these filters", noMatchesCopy: "Change the keyword or filters and try again.",
    noItems: "No collected updates yet", noItemsCopy: "Items will appear after the first successful collection.",
    error: "Unable to load the published feed", errorTitle: "The current published content is unavailable", errorCopy: "Please try again later.",
    demoFooter: "This screen contains fictional data and must not be used for operational decisions.", demoResult: " (fictional demo updates)", demoLink: "Open official source example"
  };
  const el = {
    demo: document.querySelector("#demo-banner"), recovery: document.querySelector("#recovery-banner"), recoveryCopy: document.querySelector("#recovery-banner-copy"),
    notice: document.querySelector("#unofficial-notice"), stamp: document.querySelector("#week-stamp"), form: document.querySelector("#filter-form"),
    source: document.querySelector("#source-filter"), type: document.querySelector("#priority-filter"), typeLabel: document.querySelector("#priority-filter-label"), query: document.querySelector("#query-filter"), reset: document.querySelector("#reset-button"),
    summary: document.querySelector("#result-summary"), list: document.querySelector("#update-list"), empty: document.querySelector("#empty-state"), emptyTitle: document.querySelector("#empty-title"), emptyCopy: document.querySelector("#empty-copy"),
    footer: document.querySelector("#tracker-footer"), en: document.querySelector("#locale-en"), ja: document.querySelector("#locale-ja")
  };
  const state = { source: "all", type: "all", q: "" };

  // The fictional demo is intentionally Japanese-only; never present it as translated production data.
  if (demoMode && locale !== "ja" && !fixtureMode) {
    const destination = new URL("./ja/", window.location.href);
    destination.search = "?demo=1";
    window.location.replace(destination.href);
    return;
  }

  function make(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function retainedQuery() {
    const query = new URLSearchParams();
    if (!demoMode) {
      for (const key of ["source", "type", "q", "personal-fixture"]) {
        const value = params.get(key);
        if (value) query.set(key, value.slice(0, 160));
      }
    }
    return query;
  }

  function setupLocaleLinks() {
    const query = retainedQuery();
    const english = new URL(locale === "ja" ? "../" : "./", window.location.href);
    const japanese = new URL(locale === "ja" ? "./" : "./ja/", window.location.href);
    english.search = query.toString();
    japanese.search = query.toString();
    el.en.href = `${english.pathname}${english.search}`;
    el.ja.href = `${japanese.pathname}${japanese.search}`;
  }

  function setOptions(select, options, selected) {
    select.replaceChildren(...options.map(({ value, label }) => {
      const option = make("option", "", label);
      option.value = value;
      option.selected = value === selected;
      return option;
    }));
  }

  function presentation(item) {
    const value = item.presentation;
    if (value?.schemaVersion === "meta-ads-personal-feed-presentation/v2") {
      const result = value.locales?.[locale];
      if ((result?.status === "machine" || result?.status === "reviewed") && result.shortHeadline && result.summary) return result;
    }
    if (locale === "ja" && value?.status === "generated" && value.shortHeadlineJa && value.summaryJa) {
      return { status: "machine", shortHeadline: value.shortHeadlineJa, summary: value.summaryJa };
    }
    return { status: "missing", shortHeadline: null, summary: null };
  }

  function headline(item) { return presentation(item).shortHeadline || item.title; }

  function fact(label, value, fallback = words.unknown) {
    const wrapper = make("div");
    wrapper.append(make("dt", "fact-label", label), make("dd", value ? "" : "not-stated not-stated--plain", value || fallback));
    return wrapper;
  }

  function detailUrl(item) {
    const query = new URLSearchParams({ id: item.id });
    if (state.source !== "all") query.set("source", state.source);
    if (state.type !== "all") query.set("type", state.type);
    if (state.q.trim()) query.set("q", state.q.trim());
    const fixture = params.get("personal-fixture");
    if (fixture === "1" || fixture === "v3") query.set("personal-fixture", fixture);
    return `./detail.html?${query.toString()}`;
  }

  function personalCard(item, source) {
    const li = make("li");
    const card = make("article", `update-card update-card--${source.classification}`);
    const heading = make("div", "card-heading");
    const official = source.classification === "official";
    heading.append(make("span", official ? "origin-label origin-label--official" : "origin-label origin-label--unofficial", official ? words.official : words.unofficial), make("p", "source-name", source.name));
    const facts = make("dl", "fact-grid");
    facts.append(fact(words.published, item.publishedDate), fact(words.updated, item.updatedDate));
    const link = make("a", "detail-link", words.details);
    link.href = detailUrl(item);
    link.setAttribute("aria-label", `${headline(item)} — ${words.details}`);
    card.append(heading, make("h2", "", headline(item)), facts, link);
    li.append(card);
    return li;
  }

  function legacyCard(item) {
    const li = make("li");
    const card = make("article", "update-card");
    const heading = make("div", "card-heading");
    heading.append(make("p", "source-name", item.sourceId));
    const link = make("a", "source-link", demoMode ? words.demoLink : "Open source URL");
    link.href = item.officialUrl;
    link.target = "_blank";
    link.rel = "noreferrer";
    card.append(heading, make("h2", "", item.title), link);
    li.append(card);
    return li;
  }

  setupLocaleLinks();
  try {
    const reportPath = demoMode ? `${root}demo-latest.json` : fixtureMode ? `${root}latest.json` : `${root}personal-feed.json`;
    const response = await fetch(reportPath, { cache: "no-store" });
    if (!response.ok) throw new Error(`report HTTP ${response.status}`);
    const report = await response.json();
    const personal = personalVersions.has(report.schemaVersion);
    const sources = new Map((report.sources || []).map((source) => [source.id, source]));
    el.list.classList.toggle("update-list--personal", personal);
    const delayedRecovery = !personal && report.publication?.mode === "delayed_recovery";
    el.demo.hidden = !demoMode;
    el.recovery.hidden = !delayedRecovery;
    if (delayedRecovery) {
      el.recoveryCopy.textContent = locale === "ja"
        ? "金曜17:00 MYTの締切前candidateが不足したため、人間確認済みの回復データを表示しています。"
        : "Human-reviewed delayed recovery data is displayed because candidates were missing before the Friday 17:00 MYT cutoff.";
    }
    el.notice.hidden = !personal;
    if (demoMode) el.footer.textContent = words.demoFooter;
    if (personal) {
      el.stamp.textContent = report.generatedAt ? `${words.retrieved}: ${report.generatedAt.replace("T", " ").replace("Z", " UTC")}` : words.waiting;
      el.typeLabel.textContent = locale === "ja" ? "ソース区分" : "Source type";
      setOptions(el.source, [{ value: "all", label: words.allSources }, ...report.sources.map((source) => ({ value: source.id, label: source.name }))], "all");
      setOptions(el.type, [{ value: "all", label: words.allTypes }, { value: "official", label: words.official }, { value: "unofficial", label: words.unofficial }], "all");
      state.source = sources.has(params.get("source")) ? params.get("source") : "all";
      state.type = ["official", "unofficial"].includes(params.get("type")) ? params.get("type") : "all";
      state.q = (params.get("q") || "").slice(0, 160);
    } else {
      el.stamp.textContent = report.week?.label || "";
      const legacySources = [
        { value: "all", label: locale === "ja" ? "すべてのソース" : "All sources" },
        { value: "meta-product-news-rss", label: "Product News" },
        { value: "meta-business-sdk-releases", label: "Business SDK Releases" }
      ];
      const legacyTypes = [
        { value: "all", label: locale === "ja" ? "すべて" : "All" },
        { value: "high", label: locale === "ja" ? "高" : "High" },
        { value: "standard", label: locale === "ja" ? "標準" : "Standard" },
        { value: "low", label: locale === "ja" ? "低" : "Low" }
      ];
      setOptions(el.source, legacySources, "all");
      setOptions(el.type, legacyTypes, "all");
    }

    function updateAddress() {
      if (!personal || demoMode || fixtureMode) return;
      const next = new URLSearchParams();
      if (state.source !== "all") next.set("source", state.source);
      if (state.type !== "all") next.set("type", state.type);
      if (state.q.trim()) next.set("q", state.q.trim());
      const fixture = params.get("personal-fixture");
      if (fixture === "1" || fixture === "v3") next.set("personal-fixture", fixture);
      window.history.replaceState(null, "", `${window.location.pathname}${next.size ? `?${next}` : ""}`);
      for (const key of ["source", "type", "q"]) params.delete(key);
      next.forEach((value, key) => params.set(key, value));
      setupLocaleLinks();
    }
    function visible() {
      const needle = state.q.trim().toLocaleLowerCase(locale);
      return (report.items || []).filter((item) => {
        const source = sources.get(item.sourceId);
        const text = personal ? `${item.title} ${headline(item)}` : item.title;
        return (state.source === "all" || item.sourceId === state.source) && (state.type === "all" || (personal ? source?.classification : item.priority) === state.type) && (!needle || text.toLocaleLowerCase(locale).includes(needle));
      });
    }
    function render() {
      const items = visible();
      el.list.replaceChildren(...items.map((item) => personal ? personalCard(item, sources.get(item.sourceId)) : legacyCard(item)));
      el.empty.hidden = items.length > 0;
      if (!items.length) {
        const filtered = state.source !== "all" || state.type !== "all" || Boolean(state.q.trim());
        el.emptyTitle.textContent = filtered ? words.noMatches : personal ? words.noItems : "No updates";
        el.emptyCopy.textContent = filtered ? words.noMatchesCopy : personal ? words.noItemsCopy : "";
      }
      el.summary.textContent = personal ? `${words.shown}${items.length}${words.automatic}` : `${words.shown}${items.length}${demoMode ? words.demoResult : ""}`;
    }
    function syncControls() { el.source.value = state.source; el.type.value = state.type; el.query.value = state.q; }
    el.form.addEventListener("submit", (event) => event.preventDefault());
    el.source.addEventListener("change", () => { state.source = el.source.value; updateAddress(); render(); });
    el.type.addEventListener("change", () => { state.type = el.type.value; updateAddress(); render(); });
    el.query.addEventListener("input", () => { state.q = el.query.value; updateAddress(); render(); });
    el.reset.addEventListener("click", () => { state.source = "all"; state.type = "all"; state.q = ""; updateAddress(); syncControls(); render(); });
    syncControls();
    render();
  } catch (error) {
    el.stamp.textContent = words.error;
    el.emptyTitle.textContent = words.errorTitle;
    el.emptyCopy.textContent = words.errorCopy;
    el.empty.hidden = false;
    console.error(error);
  }
})();

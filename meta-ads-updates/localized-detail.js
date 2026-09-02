(async function localizedMetaAdsDetail() {
  "use strict";

  const params = new URLSearchParams(window.location.search);
  const locale = document.documentElement.lang === "ja" ? "ja" : "en";
  const root = locale === "ja" ? "../" : "./";
  const itemId = params.get("id");
  const personalVersions = new Set(["meta-ads-personal-feed/v1", "meta-ads-personal-feed/v2", "meta-ads-personal-feed/v3"]);
  const words = locale === "ja" ? {
    official: "Meta公式", unofficial: "非公式・未確認", summaryMissing: "要約は利用できません。原文をご確認ください。", statusMachine: "AI生成の要約", statusReviewed: "レビュー済みの要約", statusMissing: "要約なし", original: "原文タイトル", published: "発表日", updated: "最終更新日", platform: "対象", unknown: "確認できず", unclassified: "未分類", sourceOfficial: "公式ソースを開く", sourceUnofficial: "非公式ソースを開く", notFound: "記事が見つかりません", notFoundCopy: "この記事は更新または保存期間の終了により、一覧から削除された可能性があります。", invalid: "記事を特定できません", invalidCopy: "一覧へ戻り、もう一度記事を選択してください。", error: "現在の公開内容を表示できません", errorCopy: "公開フィードを読み込めませんでした。しばらくしてからもう一度お試しください。"
  } : {
    official: "Official", unofficial: "Unofficial", summaryMissing: "Summary not available. Review the original source.", statusMachine: "Machine-generated summary", statusReviewed: "Reviewed summary", statusMissing: "Summary not available", original: "Original title", published: "Published", updated: "Updated", platform: "Platforms", unknown: "Not found", unclassified: "Unclassified", sourceOfficial: "Open official source", sourceUnofficial: "Open unofficial source", notFound: "Item not found", notFoundCopy: "This item may have been removed after an update or the end of its retention period.", invalid: "Unable to identify the item", invalidCopy: "Return to the feed and select the item again.", error: "The current published content is unavailable", errorCopy: "Please try again later."
  };
  const platformNames = locale === "ja" ? { "meta-platforms": "Metaプラットフォーム全般", "meta-business-sdk": "Meta Business SDK", "marketing-api": "Marketing API", "meta-ads": "Meta Ads" } : { "meta-platforms": "Meta platforms", "meta-business-sdk": "Meta Business SDK", "marketing-api": "Marketing API", "meta-ads": "Meta Ads" };
  const el = { back: document.querySelector("#back-link"), en: document.querySelector("#locale-en"), ja: document.querySelector("#locale-ja"), notice: document.querySelector("#detail-unofficial-notice"), card: document.querySelector("#detail-card"), heading: document.querySelector("#detail-heading"), title: document.querySelector("#detail-title"), summary: document.querySelector("#detail-summary"), status: document.querySelector("#detail-presentation-status"), original: document.querySelector("#detail-original-title"), facts: document.querySelector("#detail-facts"), sourceLink: document.querySelector("#detail-source-link"), error: document.querySelector("#detail-error"), errorTitle: document.querySelector("#detail-error-title"), errorCopy: document.querySelector("#detail-error-copy") };

  function make(tag, className, text) { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; }
  function safeHttps(value) { try { const url = new URL(value); return url.protocol === "https:" ? url.href : null; } catch { return null; } }
  function selectedQuery() {
    const query = new URLSearchParams();
    for (const key of ["id", "source", "type", "q", "personal-fixture"]) { const value = params.get(key); if (value) query.set(key, value.slice(0, 160)); }
    return query;
  }
  function setHref(element, path, query) { const url = new URL(path, window.location.href); url.search = query.toString(); element.href = `${url.pathname}${url.search}`; }
  function setupNavigation() {
    const listQuery = new URLSearchParams();
    for (const key of ["source", "type", "q", "personal-fixture"]) { const value = params.get(key); if (value) listQuery.set(key, value.slice(0, 160)); }
    setHref(el.back, "./", listQuery);
    const fullQuery = selectedQuery();
    setHref(el.en, locale === "ja" ? "../detail.html" : "./detail.html", fullQuery);
    setHref(el.ja, locale === "ja" ? "./detail.html" : "./ja/detail.html", fullQuery);
    const origin = "https://ysmsnsmr.github.io/meta-ads-updates/";
    const enPath = `detail.html${fullQuery.size ? `?${fullQuery}` : ""}`;
    const jaPath = `ja/detail.html${fullQuery.size ? `?${fullQuery}` : ""}`;
    document.querySelector("#canonical-link").href = `${origin}${locale === "ja" ? jaPath : enPath}`;
    document.querySelector("#alternate-en").href = `${origin}${enPath}`;
    document.querySelector("#alternate-ja").href = `${origin}${jaPath}`;
    document.querySelector("#alternate-default").href = `${origin}${enPath}`;
  }
  function presentation(item) {
    const value = item.presentation;
    if (value?.schemaVersion === "meta-ads-personal-feed-presentation/v2") {
      const result = value.locales?.[locale];
      if ((result?.status === "machine" || result?.status === "reviewed") && result.shortHeadline && result.summary) return result;
    }
    if (locale === "ja" && value?.status === "generated" && value.shortHeadlineJa && value.summaryJa) return { status: "machine", shortHeadline: value.shortHeadlineJa, summary: value.summaryJa };
    return { status: "missing", shortHeadline: null, summary: null };
  }
  function appendFact(label, value, fallback) { const wrapper = make("div"); wrapper.append(make("dt", "fact-label", label), make("dd", value ? "" : "not-stated not-stated--plain", value || fallback)); el.facts.append(wrapper); }
  function showError(title, copy) { el.card.hidden = true; el.notice.hidden = true; el.errorTitle.textContent = title; el.errorCopy.textContent = copy; el.error.hidden = false; }

  setupNavigation();
  if (!itemId || itemId.length > 160) { showError(words.invalid, words.invalidCopy); return; }
  try {
    const response = await fetch(`${root}personal-feed.json`, { cache: "no-store" });
    if (!response.ok) throw new Error(`report HTTP ${response.status}`);
    const report = await response.json();
    if (!personalVersions.has(report.schemaVersion)) throw new Error("unsupported report");
    const item = Array.isArray(report.items) ? report.items.find((candidate) => candidate.id === itemId) : null;
    const source = item && Array.isArray(report.sources) ? report.sources.find((candidate) => candidate.id === item.sourceId) : null;
    const sourceUrl = item && safeHttps(item.url);
    if (!item || !source || !sourceUrl) { showError(words.notFound, words.notFoundCopy); return; }
    const result = presentation(item);
    const official = source.classification === "official";
    el.heading.append(make("span", official ? "origin-label origin-label--official" : "origin-label origin-label--unofficial", official ? words.official : words.unofficial), make("p", "source-name", source.name));
    el.title.textContent = result.shortHeadline || item.title;
    el.summary.textContent = result.summary || words.summaryMissing;
    el.status.textContent = result.status === "machine" ? words.statusMachine : result.status === "reviewed" ? words.statusReviewed : words.statusMissing;
    el.status.className = `presentation-status presentation-status--${result.status}`;
    el.original.textContent = item.title;
    appendFact(words.published, item.publishedDate, words.unknown);
    appendFact(words.updated, item.updatedDate, words.unknown);
    const platforms = Array.isArray(item.platformIds) ? item.platformIds.map((id) => platformNames[id] || id).join(" / ") : Array.isArray(item.platforms) ? item.platforms.join(" / ") : null;
    appendFact(words.platform, platforms, words.unclassified);
    el.sourceLink.href = sourceUrl;
    el.sourceLink.textContent = official ? words.sourceOfficial : words.sourceUnofficial;
    el.notice.hidden = official;
    el.card.hidden = false;
    document.title = `${el.title.textContent} | Meta Ads Update Feed`;
  } catch (error) {
    showError(words.error, words.errorCopy);
    console.error(error);
  }
})();

(async function localizedMetaAdsFeed() {
  "use strict";

  const params = new URLSearchParams(window.location.search);
  const locale = document.documentElement.lang === "ja" ? "ja" : "en";
  const demoMode = params.get("demo") === "1";
  const fixtureMode = params.has("fixture");
  const root = locale === "ja" ? "../" : "./";
  const personalVersions = new Set(["meta-ads-personal-feed/v1", "meta-ads-personal-feed/v2", "meta-ads-personal-feed/v3", "meta-ads-personal-feed/v4", "meta-ads-personal-feed/v5"]);
  const words = locale === "ja" ? {
    allSources: "すべてのソース", allTypes: "すべて", official: "Meta公式", unofficial: "非公式",
    retrieved: "最終取得", waiting: "初回取得待ち", shown: "表示中：", automatic: "件（自動取得・要確認）",
    published: "発表日", updated: "最終更新日", observed: "初回発見日", unknown: "確認できず", addFavorite: "お気に入りに追加", removeFavorite: "お気に入りから削除",
    noMatches: "条件に一致する更新はありません", noMatchesCopy: "検索語または絞り込み条件を変更してください。",
    noItems: "取得済みの情報はありません", noItemsCopy: "初回取得後にソースからの情報を表示します。",
    error: "公開フィードを読み込めません", errorTitle: "現在の公開内容を表示できません", errorCopy: "公開フィードを読み込めませんでした。しばらくしてからもう一度お試しください。",
    officialGroup: "Meta公式", sdkGroup: "SDK更新ログ", sdkLink: "GitHub Releaseを開く", unofficialGroup: "非公式", groupCount: "{count}件",
    demoFooter: "この画面は架空データによるデモです。実運用の承認・判断には使用しないでください。", demoResult: "（デモ用の架空更新）", demoLink: "公式ソース例を開く"
  } : {
    allSources: "All sources", allTypes: "All", official: "Official", unofficial: "Unofficial",
    retrieved: "Last retrieved", waiting: "Waiting for first retrieval", shown: "Showing ", automatic: " items · automatically collected, verify before use",
    published: "Published", updated: "Updated", observed: "First found", unknown: "Not found", addFavorite: "Add to favorites", removeFavorite: "Remove from favorites",
    noMatches: "No updates match these filters", noMatchesCopy: "Change the keyword or filters and try again.",
    noItems: "No collected updates yet", noItemsCopy: "Items will appear after the first successful collection.",
    error: "Unable to load the published feed", errorTitle: "The current published content is unavailable", errorCopy: "Please try again later.",
    officialGroup: "Official updates", sdkGroup: "SDK update log", sdkLink: "Open GitHub Release", unofficialGroup: "Unofficial", groupCount: "{count} items",
    demoFooter: "This screen contains fictional data and must not be used for operational decisions.", demoResult: " (fictional demo updates)", demoLink: "Open official source example"
  };
  const el = {
    demo: document.querySelector("#demo-banner"), recovery: document.querySelector("#recovery-banner"), recoveryCopy: document.querySelector("#recovery-banner-copy"),
    notice: document.querySelector("#unofficial-notice"), stamp: document.querySelector("#week-stamp"), form: document.querySelector("#filter-form"),
    query: document.querySelector("#query-filter"),
    summary: document.querySelector("#result-summary"), legacy: document.querySelector("#legacy-list-section"), list: document.querySelector("#update-list"), officialGroup: document.querySelector("#official-group"), officialCount: document.querySelector("#official-group-count"), officialList: document.querySelector("#official-list"), sdkGroup: document.querySelector("#sdk-group"), sdkHeading: document.querySelector("#sdk-group-heading"), sdkList: document.querySelector("#sdk-list"), unofficialGroup: document.querySelector("#unofficial-group"), unofficialCount: document.querySelector("#unofficial-group-count"), unofficialList: document.querySelector("#unofficial-list"), empty: document.querySelector("#empty-state"), emptyTitle: document.querySelector("#empty-title"), emptyCopy: document.querySelector("#empty-copy"),
    footer: document.querySelector("#tracker-footer"), en: document.querySelector("#locale-en"), ja: document.querySelector("#locale-ja"), tags: document.querySelector("#featured-tags")
  };
  const state = { q: "", tag: "" };

  function malaysiaTimestamp(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    const parts = Object.fromEntries(new Intl.DateTimeFormat("en-GB", {
      timeZone: "Asia/Kuala_Lumpur", year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23"
    }).formatToParts(date).map(({ type, value: part }) => [type, part]));
    return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second} MYT`;
  }

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
      for (const key of ["q", "tag", "personal-fixture"]) {
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

  function presentation(item) {
    const value = item.presentation;
    if (value?.schemaVersion === "meta-ads-personal-feed-presentation/v3") {
      const fields = value.locales?.[locale]?.fields;
      const headline = fields?.shortHeadline;
      const summary = fields?.summary;
      const complete = [headline, summary].every((field) => field?.status === "machine" || field?.status === "reviewed");
      return { status: complete ? "machine" : "missing", shortHeadline: headline?.value || null, summary: summary?.value || null };
    }
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

  function countLabel(template, count) { return template.replace("{count}", String(count)); }

  function detailUrl(item) {
    const query = new URLSearchParams({ id: item.id });
    if (state.q.trim()) query.set("q", state.q.trim());
    if (state.tag) query.set("tag", state.tag);
    const fixture = params.get("personal-fixture");
    if (["1", "v3", "v4", "v5", "fields"].includes(fixture)) query.set("personal-fixture", fixture);
    return `./detail.html?${query.toString()}`;
  }

  function favoriteButton(item) {
    const key = item.url;
    if (!window.MetaAdsFavorites || !key) return null;
    const button = make("button", "favorite-button");
    const update = (isFavorite) => {
      button.textContent = isFavorite ? "★" : "☆";
      button.setAttribute("aria-pressed", String(isFavorite));
      button.setAttribute("aria-label", isFavorite ? words.removeFavorite : words.addFavorite);
      button.title = isFavorite ? words.removeFavorite : words.addFavorite;
    };
    update(window.MetaAdsFavorites.contains(key));
    button.addEventListener("click", () => update(window.MetaAdsFavorites.toggle(key)));
    return button;
  }

  function personalCard(item, source) {
    const li = make("li");
    const card = make("article", `update-card update-card--${source.classification}`);
    const itemPresentation = presentation(item);
    const heading = make("div", "card-heading");
    const official = source.classification === "official";
    heading.append(make("span", official ? "origin-label origin-label--official" : "origin-label origin-label--unofficial", official ? words.official : words.unofficial), make("p", "source-name", source.name));
    const favorite = favoriteButton(item);
    const titleText = itemPresentation.shortHeadline || item.title;
    const titleLink = make("a", "update-title-link", titleText);
    titleLink.href = detailUrl(item);
    titleLink.setAttribute("aria-label", titleText);
    const title = make("h2");
    title.append(titleLink);
    const main = make("div", "update-main");
    main.append(title);
    if (itemPresentation.status === "machine" && itemPresentation.shortHeadline && itemPresentation.summary) {
      main.append(make("p", "update-summary", itemPresentation.summary));
    }
    const dates = make("div", "list-dates");
    for (const [label, value] of [[words.published, item.publishedDate], [words.updated, item.updatedDate]]) {
      if (!value) continue;
      const date = make("time", "", `${label}: ${value}`);
      date.dateTime = value;
      dates.append(date);
    }
    if (!item.publishedDate && !item.updatedDate && item.firstObservedAt) {
      const date = make("time", "", `${words.observed}: ${item.firstObservedAt.slice(0, 10)}`);
      date.dateTime = item.firstObservedAt;
      dates.append(date);
    }
    card.append(main);
    if (favorite) card.append(favorite);
    card.append(heading);
    if (dates.childElementCount) card.append(dates);
    li.append(card);
    return li;
  }

  function sdkLogItem(item) {
    const li = make("li", "sdk-update-log-item");
    const date = item.updatedDate || item.publishedDate;
    const version = make("span", "sdk-update-log-version", item.title);
    const timestamp = make("time", "sdk-update-log-date", date || words.unknown);
    if (date) timestamp.dateTime = date;
    const link = make("a", "sdk-update-log-link", words.sdkLink);
    link.href = item.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.setAttribute("aria-label", `${item.title} — ${words.sdkLink}`);
    li.append(version, timestamp, link);
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
    el.officialList.classList.toggle("update-list--personal", personal);
    el.unofficialList.classList.toggle("update-list--personal", personal);
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
      el.stamp.textContent = report.generatedAt ? `${words.retrieved}: ${malaysiaTimestamp(report.generatedAt)}` : words.waiting;
      el.sdkHeading.textContent = words.sdkGroup;
      state.q = (params.get("q") || "").slice(0, 160);
      state.tag = window.MetaAdsTags?.tags.some((tag) => tag.id === params.get("tag")) ? params.get("tag") : "";
    } else {
      el.stamp.textContent = report.week?.label || "";
    }

    function updateAddress() {
      if (!personal || demoMode || fixtureMode) return;
      const next = new URLSearchParams();
      if (state.q.trim()) next.set("q", state.q.trim());
      if (state.tag) next.set("tag", state.tag);
      const fixture = params.get("personal-fixture");
      if (["1", "v3", "v4", "v5", "fields"].includes(fixture)) next.set("personal-fixture", fixture);
      window.history.replaceState(null, "", `${window.location.pathname}${next.size ? `?${next}` : ""}`);
      for (const key of ["source", "type", "q", "tag"]) params.delete(key);
      next.forEach((value, key) => params.set(key, value));
      setupLocaleLinks();
    }
    function visible() {
      const needle = state.q.trim().toLocaleLowerCase(locale);
      return (report.items || []).filter((item) => {
        const texts = personal && window.MetaAdsTags ? window.MetaAdsTags.texts(item) : [item.title];
        return (!needle || texts.some((text) => typeof text === "string" && text.toLocaleLowerCase(locale).includes(needle))) && (!state.tag || window.MetaAdsTags.matches(item, state.tag));
      }).sort((left, right) => {
        const newest = (item) => [item.publishedDate, item.updatedDate].filter(Boolean).sort().pop() || item.firstObservedAt || "";
        return newest(right).localeCompare(newest(left)) || String(right.id).localeCompare(String(left.id));
      });
    }
    function render() {
      const items = visible();
      if (el.tags && personal && !demoMode && window.MetaAdsTags) {
        const shownTags = window.MetaAdsTags.tags.slice(0, 5);
        const activeTag = window.MetaAdsTags.tags.find((tag) => tag.id === state.tag);
        if (activeTag && !shownTags.includes(activeTag)) shownTags.push(activeTag);
        const featured = shownTags.map((tag) => {
          const active = tag.id === state.tag;
          const link = make("a", "tag-chip", `${tag[locale]}${active ? " ×" : ""}`);
          link.dataset.tagId = tag.id;
          const target = new URLSearchParams();
          if (state.q.trim()) target.set("q", state.q.trim());
          if (!active) target.set("tag", tag.id);
          const fixture = params.get("personal-fixture");
          if (["1", "v3", "v4", "v5", "fields"].includes(fixture)) target.set("personal-fixture", fixture);
          link.href = target.size ? `?${target}` : "./";
          if (active) { link.setAttribute("aria-current", "true"); link.setAttribute("aria-label", locale === "ja" ? `${tag.ja}の選択を解除` : `Clear ${tag.en} tag`); }
          link.addEventListener("click", (event) => {
            if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
            event.preventDefault(); state.tag = active ? "" : tag.id; updateAddress(); render();
            el.tags.querySelector(`[data-tag-id="${tag.id}"]`)?.focus();
          });
          return link;
        });
        const all = make("a", "tag-chip tag-chip--all", locale === "ja" ? "すべてのタグ" : "All tags");
        all.href = "./tags.html";
        el.tags.replaceChildren(...featured, all);
      }
      const groups = { official: [], sdk: [], unofficial: [] };
      if (personal) {
        for (const item of items) {
          const source = sources.get(item.sourceId);
          if (item.sourceId === "meta-business-sdk-releases") groups.sdk.push(item);
          else if (source?.classification === "unofficial") groups.unofficial.push(item);
          else groups.official.push(item);
        }
        for (const [list, section, count, target] of [
          [groups.official, el.officialGroup, el.officialCount, el.officialList],
          [groups.unofficial, el.unofficialGroup, el.unofficialCount, el.unofficialList],
        ]) {
          target.replaceChildren(...list.map((item) => personalCard(item, sources.get(item.sourceId))));
          section.hidden = list.length === 0;
          count.textContent = countLabel(words.groupCount, list.length);
        }
        el.sdkList.replaceChildren(...groups.sdk.map(sdkLogItem));
        el.sdkGroup.hidden = groups.sdk.length === 0;
        el.legacy.hidden = true;
      } else {
        el.list.replaceChildren(...items.map((item) => legacyCard(item)));
        el.legacy.hidden = false;
        el.officialGroup.hidden = true;
        el.sdkGroup.hidden = true;
        el.unofficialGroup.hidden = true;
      }
      el.empty.hidden = items.length > 0;
      if (!items.length) {
        const filtered = Boolean(state.q.trim()) || Boolean(state.tag);
        el.emptyTitle.textContent = filtered ? words.noMatches : personal ? words.noItems : "No updates";
        el.emptyCopy.textContent = filtered ? words.noMatchesCopy : personal ? words.noItemsCopy : "";
      }
      el.summary.textContent = personal
          ? `${words.shown}${items.length}${words.automatic}`
          : `${words.shown}${items.length}${demoMode ? words.demoResult : ""}`;
    }
    el.form.addEventListener("submit", (event) => event.preventDefault());
    el.query.addEventListener("input", () => { state.q = el.query.value; updateAddress(); render(); });
    el.query.value = state.q;
    render();
  } catch (error) {
    el.stamp.textContent = words.error;
    el.emptyTitle.textContent = words.errorTitle;
    el.emptyCopy.textContent = words.errorCopy;
    el.empty.hidden = false;
    console.error(error);
  }
})();

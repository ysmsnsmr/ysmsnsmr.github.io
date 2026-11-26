(async function localizedMetaAdsFeed() {
  "use strict";

  const params = new URLSearchParams(window.location.search);
  const locale = document.documentElement.lang === "ja" ? "ja" : "en";
  const demoMode = params.get("demo") === "1";
  const fixtureMode = params.has("fixture");
  const headingLanguages = new Map([["zh-Hans", "简体中文"], ["es", "Español"], ["ko", "한국어"]]);
  const headingLocale = locale === "en" && !demoMode && !fixtureMode && headingLanguages.has(params.get("lang")) ? params.get("lang") : null;
  const translated = new Map();
  const root = locale === "ja" ? "../" : "./";
  const personalVersions = new Set(["meta-ads-personal-feed/v1", "meta-ads-personal-feed/v2", "meta-ads-personal-feed/v3", "meta-ads-personal-feed/v4", "meta-ads-personal-feed/v5"]);
  const words = locale === "ja" ? {
    allSources: "すべてのソース", allTypes: "すべて", official: "Meta公式", unofficial: "非公式",
    retrieved: "最終取得", waiting: "初回取得待ち", shown: "表示中：", automatic: "件（自動取得・要確認）",
    unknown: "確認できず", addFavorite: "お気に入りに追加", removeFavorite: "お気に入りから削除",
    noMatches: "条件に一致する更新はありません", noMatchesCopy: "検索語または絞り込み条件を変更してください。",
    noItems: "取得済みの情報はありません", noItemsCopy: "初回取得後にソースからの情報を表示します。",
    error: "公開フィードを読み込めません", errorTitle: "現在の公開内容を表示できません", errorCopy: "公開フィードを読み込めませんでした。しばらくしてからもう一度お試しください。",
    officialGroup: "Meta公式", sdkGroup: "SDK更新ログ", sdkLink: "GitHub Releaseを開く", unofficialGroup: "非公式", groupCount: "{count}件",
    demoFooter: "この画面は架空データによるデモです。実運用の承認・判断には使用しないでください。", demoResult: "（デモ用の架空更新）", demoLink: "公式ソース例を開く"
  } : {
    allSources: "All sources", allTypes: "All", official: "Official", unofficial: "Unofficial",
    retrieved: "Last retrieved", waiting: "Waiting for first retrieval", shown: "Showing ", automatic: " items · automatically collected, verify before use",
    unknown: "Not found", addFavorite: "Add to favorites", removeFavorite: "Remove from favorites",
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
  if (headingLocale) {
    const copy = {
      "zh-Hans": {
        common: ["语言","搜索更新","关键词","搜索标题和摘要","标签","标签表示标题或 AI 摘要中提到的内容，不一定是文章主题。","跳转到文章分区","关于非官方信息","非官方来源仅供参考，不代表 Meta 的官方立场。做出重要决定前，请核对其他来源和实际环境。","↑ 返回顶部","官方与非官方信息分开展示。"],
        words: {official:"官方", unofficial:"非官方", officialGroup:"Meta 官方更新", unofficialGroup:"非官方更新", groupCount:"{count} 篇", retrieved:"上次获取", waiting:"等待首次获取", shown:"显示 ", automatic:" 篇 · 自动获取，请核实", addFavorite:"添加到收藏", removeFavorite:"取消收藏", noMatches:"没有符合条件的文章", noMatchesCopy:"请更改关键词或标签。", noItems:"暂无文章", noItemsCopy:"首次成功获取后将显示文章。", error:"无法加载资讯", errorTitle:"暂时无法显示资讯", errorCopy:"请稍后重试。", sdkGroup:"SDK 更新日志", sdkLink:"打开 GitHub 版本", allTags:"所有标签", clearTag:"取消选择标签"}
      },
      es: {
        common: ["Idioma","Buscar novedades","Palabra clave","Buscar en titulares y resúmenes","Etiquetas","Las etiquetas indican menciones en titulares y resúmenes de IA; no siempre son el tema principal.","Ir a una sección","Acerca de la información no oficial","Las fuentes no oficiales sirven de referencia y no representan la postura de Meta. Antes de tomar decisiones importantes, consulta otras fuentes y comprueba tu entorno.","↑ Volver arriba","La información oficial y no oficial se muestra por separado."],
        words: {official:"Oficial", unofficial:"No oficial", officialGroup:"Novedades oficiales de Meta", unofficialGroup:"Novedades no oficiales", groupCount:"{count} artículos", retrieved:"Última actualización", waiting:"Pendiente de la primera actualización", shown:"Se muestran ", automatic:" artículos · recopilación automática, verifica la información", addFavorite:"Añadir a favoritos", removeFavorite:"Quitar de favoritos", noMatches:"No hay artículos que coincidan", noMatchesCopy:"Cambia la palabra clave o la etiqueta.", noItems:"Todavía no hay artículos", noItemsCopy:"Los artículos aparecerán después de la primera actualización.", error:"No se pudieron cargar las novedades", errorTitle:"No se pueden mostrar las novedades", errorCopy:"Inténtalo de nuevo más tarde.", sdkGroup:"Registro de actualizaciones del SDK", sdkLink:"Abrir la versión en GitHub", allTags:"Todas las etiquetas", clearTag:"Quitar etiqueta"}
      },
      ko: {
        common: ["언어","업데이트 검색","검색어","제목 및 요약 검색","태그","태그는 제목이나 AI 요약에서 언급된 내용을 나타내며, 기사의 주제와 다를 수 있습니다.","기사 섹션으로 이동","비공식 정보 안내","비공식 출처는 참고용이며 Meta의 공식 입장이 아닙니다. 중요한 결정을 내리기 전에 다른 출처와 실제 환경에서 확인하세요.","↑ 맨 위로","공식 정보와 비공식 정보를 구분해 표시합니다."],
        words: {official:"공식", unofficial:"비공식", officialGroup:"Meta 공식 업데이트", unofficialGroup:"비공식 업데이트", groupCount:"{count}건", retrieved:"마지막 수집", waiting:"첫 수집 대기 중", shown:"표시 중: ", automatic:"건 · 자동 수집, 확인 필요", addFavorite:"즐겨찾기에 추가", removeFavorite:"즐겨찾기에서 삭제", noMatches:"조건과 일치하는 기사가 없습니다", noMatchesCopy:"검색어나 태그를 변경하세요.", noItems:"수집된 기사가 없습니다", noItemsCopy:"첫 수집에 성공하면 기사가 표시됩니다.", error:"업데이트를 불러올 수 없습니다", errorTitle:"업데이트를 표시할 수 없습니다", errorCopy:"잠시 후 다시 시도하세요.", sdkGroup:"SDK 업데이트 기록", sdkLink:"GitHub 릴리스 열기", allTags:"모든 태그", clearTag:"태그 해제"}
      }
    }[headingLocale];
    Object.assign(words, copy.words);
    document.documentElement.lang = headingLocale;
    const [language, search, keyword, placeholder, tags, hint, jumps, notice, warning, top, footer] = copy.common;
    el.en.parentElement.setAttribute("aria-label", language);
    el.form.closest(".control-panel").setAttribute("aria-label", search);
    el.form.querySelector('label[for="query-filter"]').textContent = keyword;
    el.query.placeholder = placeholder;
    el.tags.setAttribute("aria-label", tags);
    el.form.querySelector(".tag-hint").textContent = hint;
    const navigation = document.querySelector("#feed-jumps");
    navigation.setAttribute("aria-label", jumps);
    navigation.querySelector('[href="#official-group"]').textContent = words.official;
    navigation.querySelector('[href="#unofficial-group"]').textContent = words.unofficial;
    document.querySelector("#official-group-heading").textContent = words.officialGroup;
    document.querySelector("#unofficial-group-heading").textContent = words.unofficialGroup;
    el.notice.setAttribute("aria-label", notice);
    el.notice.querySelector("strong").textContent = notice;
    el.notice.querySelector("span").textContent = warning;
    document.querySelector('main > a[href="#top"]').textContent = top;
    el.footer.textContent = footer;
  }
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
    if (!demoMode && !fixtureMode) {
      el.en.parentElement.classList.add("locale-switch--headlines");
      for (const [code, label] of headingLanguages) {
        let link = document.querySelector(`#headline-language-${code}`);
        if (!link) {
          link = make("a", "", label);
          link.id = `headline-language-${code}`;
          link.lang = code;
          el.en.parentElement.append(link);
        }
        const target = new URL(english);
        target.searchParams.set("lang", code);
        link.href = target.href;
        if (code === headingLocale) link.setAttribute("aria-current", "page");
      }
      if (headingLocale) el.en.removeAttribute("aria-current");
    }
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

  function headline(item) { return translated.get(item.id) || presentation(item).shortHeadline || item.title; }

  function countLabel(template, count) { return template.replace("{count}", String(count)); }

  function detailUrl(item) {
    const query = new URLSearchParams({ id: item.id });
    if (headingLocale) query.set("fromLang", headingLocale);
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
    const favorite = favoriteButton(item);
    const titleText = headline(item);
    const titleLink = make("a", "update-title-link", titleText);
    if (translated.has(item.id)) titleLink.lang = headingLocale;
    titleLink.href = detailUrl(item);
    titleLink.setAttribute("aria-label", titleText);
    const title = make("h2");
    title.append(titleLink);
    const main = make("div", "update-main");
    main.append(title);
    if (!headingLocale && itemPresentation.status === "machine" && itemPresentation.shortHeadline && itemPresentation.summary) {
      main.append(make("p", "update-summary", itemPresentation.summary));
    }
    card.append(main);
    if (favorite) card.append(favorite);
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
  if (headingLocale) {
    const notices = {
      "zh-Hans": "仅翻译标题；无译文时显示英文。文章详情为英文。",
      es: "Solo se traducen los titulares. Si no hay traducción, se muestra el inglés. Los detalles están en inglés.",
      ko: "제목만 번역됩니다. 번역이 없으면 영어로 표시되며, 상세 페이지는 영어입니다."
    };
    const note = make("p", "headline-language-note", notices[headingLocale]);
    note.lang = headingLocale;
    el.form.before(note);
  }
  try {
    const reportPath = demoMode ? `${root}demo-latest.json` : fixtureMode ? `${root}latest.json` : `${root}personal-feed.json`;
    const response = await fetch(reportPath, { cache: "no-store" });
    if (!response.ok) throw new Error(`report HTTP ${response.status}`);
    const report = await response.json();
    const personal = personalVersions.has(report.schemaVersion);
    if (personal && headingLocale && window.crypto?.subtle) {
      try {
        const overlayResponse = await fetch(`${root}headline-translations.json`, { cache: "no-store", signal: AbortSignal.timeout(3000) });
        if (overlayResponse.ok) {
          const overlay = await overlayResponse.json();
          if (overlay.schemaVersion === "meta-ads-headline-translations/v1") {
            await Promise.all(report.items.map(async (item) => {
              const record = overlay.items?.[item.id]?.[headingLocale];
              if (record?.status !== "machine" || typeof record.value !== "string" || !record.value.trim() || record.value.length > 480) return;
              const input = JSON.stringify(["headline-translation-v2-original-title", headingLocale, item.title]);
              const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(input));
              const hash = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
              if (record.inputHash === hash) translated.set(item.id, record.value);
            }));
          }
        }
      } catch { /* English fallback when translations are unavailable. */ }
    }
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
      if (headingLocale) next.set("lang", headingLocale);
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
        const texts = personal && window.MetaAdsTags ? [...window.MetaAdsTags.texts(item), headline(item)] : [item.title];
        return (!needle || texts.some((text) => typeof text === "string" && text.toLocaleLowerCase(locale).includes(needle))) && (!state.tag || window.MetaAdsTags.matches(item, state.tag));
      }).sort((left, right) => {
        const newest = (item) => [item.publishedDate, item.updatedDate].filter(Boolean).sort().pop() || item.firstObservedAt || "";
        return newest(right).localeCompare(newest(left)) || String(right.id).localeCompare(String(left.id));
      });
    }
    function render() {
      const items = visible();
      if (el.tags && personal && !demoMode && window.MetaAdsTags) {
        const featuredIds = ["ai", "campaign", "creative", "placements", "audiences"];
        const shownTags = featuredIds.map((id) => window.MetaAdsTags.tags.find((tag) => tag.id === id)).filter(Boolean);
        if (state.tag && !featuredIds.includes(state.tag)) {
          const selected = window.MetaAdsTags.tags.find((tag) => tag.id === state.tag);
          if (selected) shownTags.push(selected);
        }
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
          if (active) { link.setAttribute("aria-current", "true"); link.setAttribute("aria-label", headingLocale ? `${words.clearTag}: ${tag.en}` : locale === "ja" ? `${tag.ja}の選択を解除` : `Clear ${tag.en} tag`); }
          link.addEventListener("click", (event) => {
            if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
            event.preventDefault(); state.tag = active ? "" : tag.id; updateAddress(); render();
            el.tags.querySelector(`[data-tag-id="${tag.id}"]`)?.focus();
          });
          return link;
        });
        const all = make("a", "tag-chip tag-chip--all", words.allTags || (locale === "ja" ? "すべてのタグ" : "All tags"));
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
      const jumps = document.querySelector("#feed-jumps");
      if (jumps) {
        jumps.querySelector('[href="#official-group"]').hidden = el.officialGroup.hidden;
        jumps.querySelector('[href="#unofficial-group"]').hidden = el.unofficialGroup.hidden;
        jumps.hidden = el.officialGroup.hidden && el.unofficialGroup.hidden;
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

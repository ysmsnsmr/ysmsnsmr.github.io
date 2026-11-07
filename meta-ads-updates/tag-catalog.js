(function () {
  "use strict";
  // Tags indicate a mention, not necessarily the article's main subject.
  // No new model output or source text is generated.
  const tags = [
    { id: "meta-muse", en: "Meta Muse", ja: "Meta Muse", pattern: /\bmuse\b|メタ\s*ミューズ/i },
    { id: "meta-one", en: "Meta One", ja: "Meta One", pattern: /\bmeta[\s-]+one\b|メタ\s*ワン/i },
    { id: "ads-manager", en: "Ads Manager", ja: "広告マネージャー", pattern: /\bads?\s+manager\b|広告マネージャー/i },
    { id: "placements", en: "Ad placements", ja: "配置", pattern: /\b(?:ad\s+)?placements?\b|広告配置|配信面/i },
    { id: "creative", en: "Creative", ja: "クリエイティブ", pattern: /\bcreatives?\b|クリエイティブ/i },
    { id: "audiences", en: "Audiences", ja: "オーディエンス", pattern: /\baudiences?\b|オーディエンス/i },
    { id: "budget", en: "Budget", ja: "予算", pattern: /\bbudgets?\b|予算/i },
    { id: "campaign", en: "Campaign", ja: "キャンペーン", pattern: /\bcampaigns?\b|キャンペーン/i },
    { id: "ai", en: "AI", ja: "AI", pattern: /\bai\b|\bartificial\s+intelligence\b|人工知能/i },
    { id: "exclusion", en: "Exclusions", ja: "除外", pattern: /\bexclud(?:e|es|ed|ing)\b|\bexclusions?\b|除外/i },
  ];
  function texts(item) {
    const p = item.presentation || {};
    const values = [item.title];
    if (p.status === "generated") values.push(p.shortHeadlineJa, p.summaryJa);
    for (const locale of ["en", "ja"]) {
      const value = p.locales?.[locale];
      if (["machine", "reviewed"].includes(value?.status)) values.push(value.shortHeadline);
      if (["machine", "reviewed"].includes(value?.fields?.shortHeadline?.status)) values.push(value.fields.shortHeadline.value);
      if (p.schemaVersion === "meta-ads-personal-feed-presentation/v3") {
        if (["machine", "reviewed"].includes(value?.fields?.summary?.status)) values.push(value.fields.summary.value);
      } else if (["machine", "reviewed"].includes(value?.status)) {
        values.push(value.summary);
      }
    }
    return values.filter((text) => typeof text === "string" && text.trim());
  }
  function matches(item, id) {
    const tag = tags.find((entry) => entry.id === id);
    return Boolean(tag && texts(item).some((text) => tag.pattern.test(text)));
  }
  window.MetaAdsTags = { tags, matches, texts };
})();

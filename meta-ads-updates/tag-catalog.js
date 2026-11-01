(function () {
  "use strict";
  // Deliberately conservative title matching: an absent tag is not evidence
  // that an article is unrelated. No source text or model output is generated.
  const tags = [
    { id: "meta-muse", en: "Meta Muse", ja: "Meta Muse", pattern: /\bmuse\b|メタ\s*ミューズ/i },
    { id: "meta-one", en: "Meta One", ja: "Meta One", pattern: /\bmeta[\s-]+one\b|メタ\s*ワン/i },
    { id: "meta-pixel", en: "Meta Pixel", ja: "Meta Pixel", pattern: /\b(?:meta|facebook)[\s-]+pixel\b|\bpixel\b|ピクセル/i },
    { id: "conversions-api", en: "Conversions API", ja: "Conversions API", pattern: /\bconversions?\s+api\b|コンバージョン(?:ズ)?\s*api/i },
    { id: "advantage-plus", en: "Advantage+", ja: "Advantage+", pattern: /\badvantage\s*(?:\+|plus\b)|アドバンテージ\s*(?:プラス|\+)/i },
    { id: "ads-manager", en: "Ads Manager", ja: "広告マネージャー", pattern: /\bads?\s+manager\b|広告マネージャー/i },
    { id: "placements", en: "Ad placements", ja: "広告配置", pattern: /\b(?:ad\s+)?placements?\b|広告配置|配信面/i },
    { id: "creative", en: "Creative", ja: "クリエイティブ", pattern: /\bcreatives?\b|クリエイティブ/i },
    { id: "audiences", en: "Audiences", ja: "オーディエンス", pattern: /\baudiences?\b|オーディエンス/i },
  ];
  function texts(item) {
    const p = item.presentation || {};
    const titles = [item.title, p.shortHeadlineJa];
    for (const locale of ["en", "ja"]) {
      const value = p.locales?.[locale];
      if (["machine", "reviewed"].includes(value?.status)) titles.push(value.shortHeadline);
      if (["machine", "reviewed"].includes(value?.fields?.shortHeadline?.status)) titles.push(value.fields.shortHeadline.value);
    }
    return titles.filter((text) => typeof text === "string" && text.trim());
  }
  function matches(item, id) {
    const tag = tags.find((entry) => entry.id === id);
    return Boolean(tag && texts(item).some((text) => tag.pattern.test(text)));
  }
  window.MetaAdsTags = { tags, matches };
})();

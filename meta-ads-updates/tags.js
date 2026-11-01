(async function () {
  "use strict";
  const locale = document.documentElement.lang === "ja" ? "ja" : "en";
  const status = document.querySelector("#tags-status");
  const list = document.querySelector("#tags-list");
  try {
    const response = await fetch(locale === "ja" ? "../personal-feed.json" : "./personal-feed.json", { cache: "no-store" });
    if (!response.ok) throw new Error("Feed unavailable");
    const report = await response.json();
    if (!Array.isArray(report.items) || !window.MetaAdsTags) throw new Error("Invalid feed");
    for (const tag of window.MetaAdsTags.tags) {
      const count = report.items.filter((item) => window.MetaAdsTags.matches(item, tag.id)).length;
      const item = document.createElement("li");
      const link = document.createElement("a");
      const name = document.createElement("span");
      const quantity = document.createElement("span");
      link.href = `./?tag=${encodeURIComponent(tag.id)}`;
      name.textContent = tag[locale];
      quantity.textContent = locale === "ja" ? `${count}件` : `${count} ${count === 1 ? "item" : "items"}`;
      quantity.className = "tag-count";
      link.append(name, quantity); item.append(link); list.append(item);
    }
    status.textContent = locale === "ja" ? `${window.MetaAdsTags.tags.length}タグ・現在の掲載記事が対象` : `${window.MetaAdsTags.tags.length} tags · Current published items`;
  } catch {
    status.textContent = locale === "ja" ? "タグを読み込めませんでした。時間をおいて再度お試しください。" : "Could not load tags. Please try again later.";
  }
})();

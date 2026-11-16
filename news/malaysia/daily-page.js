(function () {
  "use strict";

  function revealArticle(hash) {
    if (!hash || !hash.startsWith("#article-")) return;
    let id;
    try { id = decodeURIComponent(hash.slice(1)); } catch (_) { return; }
    const article = document.getElementById(id);
    if (!article) return;
    let parent = article.parentElement;
    let opened = false;
    while (parent) {
      if (parent.tagName === "DETAILS" && !parent.open) {
        parent.open = true;
        opened = true;
      }
      parent = parent.parentElement;
    }
    if (opened) requestAnimationFrame(() => {
      (article.closest(".disaster-story") || article).scrollIntoView({ block: "start" });
    });
  }

  window.addEventListener("hashchange", () => revealArticle(window.location.hash));
  window.addEventListener("pageshow", () => revealArticle(window.location.hash));
  document.addEventListener("click", (event) => {
    const anchor = event.target.closest("a[href]");
    if (anchor) revealArticle(anchor.getAttribute("href"));
  }, true);
  revealArticle(window.location.hash);

  const link = document.querySelector(".back-to-top");
  const top = document.getElementById("page-top");
  if (!link || !top) return;

  function updateVisibility() {
    link.hidden = window.scrollY < 400;
  }

  window.addEventListener("scroll", updateVisibility, { passive: true });
  window.addEventListener("pageshow", updateVisibility);
  updateVisibility();

  link.addEventListener("click", (event) => {
    event.preventDefault();
    top.focus({ preventScroll: true });
    window.scrollTo({
      top: 0,
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
    });
  });
})();

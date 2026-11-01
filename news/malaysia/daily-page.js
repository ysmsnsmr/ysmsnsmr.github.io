(function () {
  "use strict";

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

(function metaAdsFavorites() {
  "use strict";

  const storageKey = "meta-ads-update-feed:favorites/v1";
  const maximumFavorites = 1000;

  function canonicalUrl(value) {
    try {
      const url = new URL(value);
      return url.protocol === "https:" ? url.href : null;
    } catch {
      return null;
    }
  }

  function read() {
    try {
      const value = JSON.parse(window.localStorage.getItem(storageKey) || "[]");
      if (!Array.isArray(value)) return new Set();
      return new Set(value
        .filter((candidate) => typeof candidate === "string")
        .map(canonicalUrl)
        .filter(Boolean)
        .slice(0, maximumFavorites));
    } catch {
      return new Set();
    }
  }

  function write(favorites) {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify([...favorites].sort()));
    } catch {
      // A privacy setting can block local storage. The feed must stay usable without it.
    }
  }

  function contains(value) {
    const key = canonicalUrl(value);
    return Boolean(key) && read().has(key);
  }

  function toggle(value) {
    const key = canonicalUrl(value);
    if (!key) return false;
    const favorites = read();
    if (favorites.has(key)) {
      favorites.delete(key);
      write(favorites);
      return false;
    }
    if (favorites.size >= maximumFavorites) return false;
    favorites.add(key);
    write(favorites);
    return true;
  }

  window.MetaAdsFavorites = Object.freeze({ contains, toggle });
})();

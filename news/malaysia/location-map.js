(function () {
  "use strict";

  const panel = document.getElementById("news-map");
  if (!panel) return;

  const rows = Array.from(panel.querySelectorAll(".map-place"));
  const places = new Map();
  rows.forEach((row) => {
    places.set(row.dataset.placeKey, {
      row,
      latitude: Number(row.dataset.lat),
      longitude: Number(row.dataset.lon),
      zoom: Number(row.dataset.zoom),
      marker: null,
    });
  });

  let map = null;
  function initialize() {
    if (map) {
      map.invalidateSize();
      return true;
    }
    if (!window.L) {
      document.getElementById("location-map-status").hidden = false;
      return false;
    }

    map = L.map("location-map-canvas", { scrollWheelZoom: false });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);

    const coordinates = [];
    places.forEach((place) => {
      const position = [place.latitude, place.longitude];
      coordinates.push(position);
      const popup = document.createElement("div");
      const label = document.createElement("strong");
      label.textContent = place.row.querySelector("strong").textContent;
      popup.append(label);
      place.row.querySelectorAll("a").forEach((link) => {
        const articleLink = document.createElement("a");
        articleLink.href = link.getAttribute("href");
        articleLink.textContent = link.textContent;
        popup.append(articleLink);
      });
      place.marker = L.circleMarker(position, {
        radius: 7,
        color: "#00594f",
        weight: 2,
        fillColor: "#ffffff",
        fillOpacity: 1,
      }).addTo(map).bindPopup(popup);
    });
    if (coordinates.length === 1) {
      map.setView(coordinates[0], 9);
    } else {
      map.fitBounds(coordinates, { padding: [24, 24], maxZoom: 9 });
    }
    return true;
  }

  panel.addEventListener("toggle", () => {
    if (panel.open) requestAnimationFrame(initialize);
  });
  document.querySelectorAll(".place-link").forEach((link) => {
    link.addEventListener("click", (event) => {
      if (!window.L) return;
      const place = places.get(link.dataset.placeKey);
      if (!place) return;
      event.preventDefault();
      panel.open = true;
      requestAnimationFrame(() => {
        if (!initialize()) return;
        map.setView([place.latitude, place.longitude], place.zoom);
        place.marker.openPopup();
        panel.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
  });
})();

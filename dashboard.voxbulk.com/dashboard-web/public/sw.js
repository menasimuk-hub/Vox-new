/* Minimal service worker — enables Chrome install prompt for dashboard PWA */
const SW_VERSION = "voxbulk-dashboard-splash-v5";

self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  event.respondWith(fetch(event.request));
});

void SW_VERSION;
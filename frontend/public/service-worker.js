// Minimal no-op service worker to avoid 404s and enable basic lifecycle.
self.addEventListener('install', (event) => {
  // Activate immediately after installation.
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  // Take control of pages immediately.
  event.waitUntil(self.clients.claim());
});

// No fetch handler: we do not intercept network requests. This SW is intentionally inert.

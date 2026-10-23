// Cache-first for the engine files under /py/, keyed by the manifest's version,
// so repeat visits start without downloading Pyodide again.
const PREFIX = "ri-layercake-py-";

self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

async function currentCache() {
  try {
    const res = await fetch("/py/manifest.json", { cache: "no-cache" });
    const manifest = await res.json();
    const name = PREFIX + manifest.version + "-" + manifest.sha256.slice(0, 12);
    for (const key of await caches.keys()) {
      if (key.startsWith(PREFIX) && key !== name) await caches.delete(key);
    }
    return caches.open(name);
  } catch {
    return null;
  }
}

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || !url.pathname.startsWith("/py/") || url.pathname.endsWith("manifest.json")) {
    return;
  }
  event.respondWith(
    (async () => {
      const cache = await currentCache();
      if (!cache) return fetch(event.request);
      const hit = await cache.match(event.request);
      if (hit) return hit;
      const res = await fetch(event.request);
      if (res.ok) cache.put(event.request, res.clone());
      return res;
    })(),
  );
});

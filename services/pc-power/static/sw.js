// Service worker mínimo: solo existe para que el panel sea instalable.
// Estrategia network-only: no guarda NADA (ni HTML ni API), así que nunca muestra un
// estado antiguo. Sin conexión, las navegaciones reciben una página que lo dice, sin acciones.
const OFFLINE_HTML = `<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light dark">
<title>Sin conexión</title></head>
<body style="font:16px system-ui,sans-serif;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0">
<p><strong>Sin conexión</strong></p></body></html>`;

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return; // las acciones van directas a la red
  event.respondWith(
    fetch(event.request).catch(() =>
      event.request.mode === "navigate"
        ? new Response(OFFLINE_HTML, {
            status: 503,
            headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
          })
        : Response.error()
    )
  );
});

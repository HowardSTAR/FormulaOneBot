/* No fetch handler: never cache account/API responses or race assets. */
self.addEventListener("push", event => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { /* Show safe fallback. */ }
  event.waitUntil(self.registration.showNotification(String(data.title || "TurboTears"), {
    body: String(data.body || "Новое уведомление"),
    icon: "/app-icon-192-v2.png", tag: String(data.tag || "turbotears"),
    data: { url: typeof data.url === "string" ? data.url : "/notifications" },
  }));
});
self.addEventListener("notificationclick", event => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || "/notifications", self.location.origin);
  const url = target.origin === self.location.origin ? target.href : new URL("/notifications", self.location.origin).href;
  event.waitUntil(self.clients.openWindow(url));
});

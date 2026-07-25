const CACHE = 'rotina-shell-v1';
const SHELL = ['./', 'icon.svg', 'manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener('activate', e => e.waitUntil(
  caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim())
));

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  // API (Lambda) e fontes externas: sempre rede, nunca cache
  if (url.origin !== self.location.origin) return;
  if (req.mode === 'navigate') {
    // network-first: atualizações chegam na hora; cache só como fallback offline
    e.respondWith(
      fetch(req).then(r => {
        const cp = r.clone();
        caches.open(CACHE).then(c => c.put('./', cp)).catch(() => {});
        return r;
      }).catch(() => caches.match('./'))
    );
    return;
  }
  e.respondWith(
    caches.match(req).then(hit => hit || fetch(req).then(r => {
      const cp = r.clone();
      caches.open(CACHE).then(c => c.put(req, cp)).catch(() => {});
      return r;
    }))
  );
});

self.addEventListener('push', e => {
  let data = {};
  try { data = e.data ? e.data.json() : {}; } catch { data = {}; }
  const title = data.title || 'Rotina Diária';
  const body = data.body || 'Não esqueça de registrar seu dia hoje.';
  e.waitUntil(self.registration.showNotification(title, {
    body,
    icon: 'icon.svg',
    badge: 'icon.svg',
  }));
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clients => {
      for (const c of clients) { if ('focus' in c) return c.focus(); }
      if (self.clients.openWindow) return self.clients.openWindow('./');
    })
  );
});

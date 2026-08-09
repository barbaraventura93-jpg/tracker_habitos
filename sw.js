// v2: a v1 guardava o HTML e devolvia do cache sem revalidar. Como o endereço do
// Function URL é injetado no HTML no deploy, um aparelho com HTML velho ficava
// chamando um endereço que não existe mais e a API respondia 403 para tudo. O
// nome do cache mudou de propósito — o `activate` apaga a v1 inteira.
const CACHE = 'rotina-shell-v2';
// Só o que é imutável entra no shell. O HTML NÃO entra: ele carrega configuração
// que muda a cada deploy.
const SHELL = ['icon.svg', 'manifest.json'];

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
  // config.json diz onde a API está agora — passa direto para a rede, sem
  // interceptação. Servi-lo do cache recriaria o problema que ele resolve.
  if (url.pathname.endsWith('/config.json')) return;
  if (req.mode === 'navigate') {
    // network-first com `cache:'reload'`: sem isso o fetch aqui dentro ainda
    // pode ser servido pelo cache HTTP do navegador, que guarda a resposta por
    // heurística quando ela não traz Cache-Control. O cache do SW fica só como
    // último recurso offline.
    e.respondWith(
      fetch(url.href, { cache: 'reload', credentials: 'same-origin' }).then(r => {
        if (r && r.ok) {
          const cp = r.clone();
          caches.open(CACHE).then(c => c.put('./', cp)).catch(() => {});
        }
        return r;
      }).catch(() => caches.match('./').then(hit => hit || fetch(req)))
    );
    return;
  }
  // Resto do shell (ícone, manifest): responde do cache e atualiza por trás.
  e.respondWith(
    caches.match(req).then(hit => {
      const net = fetch(req).then(r => {
        if (r && r.ok) {
          const cp = r.clone();
          caches.open(CACHE).then(c => c.put(req, cp)).catch(() => {});
        }
        return r;
      });
      return hit || net;
    })
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

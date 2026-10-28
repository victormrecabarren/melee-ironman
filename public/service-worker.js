// Retire the previous CRA/Workbox worker at its existing URL. This release
// loads fresh assets from the network; saved matches remain in localStorage.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    await self.clients.claim();
    const cacheNames = await caches.keys();
    await Promise.all(cacheNames.filter(name => name.startsWith('workbox-') && name.includes(self.registration.scope))
      .map(name => caches.delete(name)));
    await self.registration.unregister();
  })());
});

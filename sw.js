// ══════════════════════════════════════════════════════════════════════════════
// Stem Player — Service Worker
//
// Two-track caching strategy:
//   • songs.json, index.html, manifest.json → NETWORK-FIRST
//     Always fetches fresh from server when online; falls back to cache offline.
//     This ensures a newly added song appears immediately on next page load.
//
//   • Audio files (.mp3, .wav, etc.) → CACHE-FIRST
//     Served from cache instantly; only hits network if not yet cached.
//     Makes offline playback fast and reliable.
//
// HOW TO FORCE a full re-cache (e.g. you replaced an audio file with same name):
//   Bump CACHE_VERSION below (v1 → v2) and re-upload sw.js.
//   All users will re-download everything on their next visit with internet.
// ══════════════════════════════════════════════════════════════════════════════
const CACHE_VERSION = 'v28';
const CACHE_NAME    = 'stem-player-' + CACHE_VERSION;

const AUDIO_EXT = /\.(mp3|wav|m4a|aiff|ogg|flac)(\?.*)?$/i;

// ── Install: pre-cache app shell + all audio files in songs.json ──────────────
self.addEventListener('install', event => {
    event.waitUntil(
        (async () => {
            const cache = await caches.open(CACHE_NAME);

            // Cache the app shell
            await cache.addAll(['./', './index.html', './songs.json', './manifest.json']);

            // Read songs.json and pre-cache every audio file it lists
            try {
                const resp = await fetch('./songs.json');
                if (resp.ok) {
                    const data  = await resp.json();
                    const songs = Array.isArray(data) ? data : (data.songs || []);
                    // Collect all audio URLs, including vamp / postVamp sections
                    const audioUrls = songs.flatMap(s => [
                        s.vocal, s.instr,
                        s.vamp?.vocal, s.vamp?.instr,
                        s.postVamp?.vocal, s.postVamp?.instr
                    ]).filter(Boolean);
                    for (const url of audioUrls) {
                        try { await cache.add(url); }
                        catch(e) { console.warn('[SW] Could not pre-cache:', url, e.message); }
                    }
                }
            } catch(e) {
                console.warn('[SW] Could not read songs.json during install:', e.message);
            }

            await self.skipWaiting();
        })()
    );
});

// ── Activate: delete stale caches ─────────────────────────────────────────────
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys()
            .then(keys => Promise.all(
                keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
            ))
            .then(() => self.clients.claim())
    );
});

// ── Fetch ─────────────────────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
    if (event.request.method !== 'GET') return;

    const url = new URL(event.request.url);

    if (AUDIO_EXT.test(url.pathname)) {
        // ── CACHE-FIRST for audio files ───────────────────────────────────────
        event.respondWith(
            caches.match(event.request).then(cached => {
                if (cached) return cached;
                // Not cached yet — fetch, cache, and return
                return fetch(event.request).then(response => {
                    if (response.ok) {
                        const clone = response.clone();
                        caches.open(CACHE_NAME).then(c => c.put(event.request, clone));
                    }
                    return response;
                }).catch(() => new Response('Audio not available offline', {
                    status: 503, headers: { 'Content-Type': 'text/plain' }
                }));
            })
        );
    } else {
        // ── NETWORK-FIRST for everything else (songs.json, HTML, manifest) ───
        event.respondWith(
            fetch(event.request)
                .then(response => {
                    // Update the cache with the fresh response
                    if (response.ok) {
                        const clone = response.clone();
                        caches.open(CACHE_NAME).then(c => c.put(event.request, clone));
                    }
                    return response;
                })
                .catch(() => {
                    // Offline — serve from cache as fallback
                    return caches.match(event.request).then(cached =>
                        cached || new Response('Offline — content not cached', {
                            status: 503, headers: { 'Content-Type': 'text/plain' }
                        })
                    );
                })
        );
    }
});

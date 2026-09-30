window.NETRIDER_PAGER = true;
window.NETRIDER_LIVE_AUTOSTART = true;
window.NETRIDER_SERVER_PORT = 8443;
window.NETRIDER_HTTP_REDIRECT_PORT = 8090;
window.NETRIDER_GEOCODER = Object.freeze({
  provider: 'Nominatim',
  reverseEndpoint: 'https://nominatim.openstreetmap.org/reverse',
  requestMode: 'jsonp',
  minimumIntervalMs: 1100,
  cachePrecision: 5
});

// The desktop build uses /api. Redirect those early startup requests to the
// Pager's small CGI API before app.js initializes its capture library.
(() => {
  const originalFetch = window.fetch.bind(window);
  window.fetch = (input, init) => {
    const source = typeof input === 'string' ? input : input.url;
    let target = source;
    if (source.startsWith('/api/captures')) target = source.replace('/api/captures', '/cgi-bin/captures.sh');
    if (source.startsWith('/api/capture')) target = source.replace('/api/capture', '/cgi-bin/capture.sh');
    return originalFetch(target, init);
  };
})();

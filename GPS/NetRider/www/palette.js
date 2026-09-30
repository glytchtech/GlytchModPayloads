(() => {
  const palettes = {
    crimson: { name: 'CRIMSON', accent: '#ff4e48', bright: '#fff7f5', secondary: '#ff8a84', grid: '#62171c', mapBackground: '#090102', mapFill: '#31080b', mapLine: '#ff5851', mapText: '#fff5f2', signalGlow: '#ff4e48', signalStroke: '#ff817a', signalCore: '#fff7f5', active: '#fff7f5', traceGlow: '#fff7f4', traceStart: '#fff7f4', traceMid: '#ffffff', traceEnd: '#fff7f4' },
    outdoor: { name: 'OUTDOOR', accent: '#1f7047', bright: '#082719', secondary: '#c45d12', grid: '#9bb5a4', mapBackground: '#f7fbf7', mapFill: '#d8e8db', mapLine: '#4e745c', mapText: '#123826', signalGlow: '#2d8c56', signalStroke: '#145f39', signalCore: '#ffffff', active: '#c45d12', traceGlow: '#075ec0', traceStart: '#075ec0', traceMid: '#123b75', traceEnd: '#075ec0' },
    contrast: { name: 'HIGH CONTRAST', accent: '#238cff', bright: '#ffffff', secondary: '#ffffff', grid: '#4d4d4d', mapBackground: '#000000', mapFill: '#151515', mapLine: '#ffffff', mapText: '#ffffff', signalGlow: '#238cff', signalStroke: '#ffffff', signalCore: '#ffffff', active: '#238cff', traceGlow: '#238cff', traceStart: '#238cff', traceMid: '#ffffff', traceEnd: '#238cff' },
    matrix: { name: 'MATRIX', accent: '#8dff78', bright: '#d7ffb8', secondary: '#e5ff45', grid: '#356b3b', mapBackground: '#020603', mapFill: '#0c2a10', mapLine: '#78ff63', mapText: '#caffb9', signalGlow: '#8dff78', signalStroke: '#8dff78', signalCore: '#d5ffcb', active: '#e5ff45', traceGlow: '#f6ffcc', traceStart: '#e5ff45', traceMid: '#ffffff', traceEnd: '#e5ff45' },
    arc: { name: 'DEEP SCAN', accent: '#42efff', bright: '#e7fdff', secondary: '#b5fbff', grid: '#1b6570', mapBackground: '#010608', mapFill: '#06323a', mapLine: '#43ebff', mapText: '#dbfcff', signalGlow: '#42efff', signalStroke: '#52efff', signalCore: '#e7fdff', active: '#b5fbff', traceGlow: '#ffe47c', traceStart: '#ffe47c', traceMid: '#ffffff', traceEnd: '#ffe47c' },
    violet: { name: 'GHOST', accent: '#fa54f5', bright: '#ffeaff', secondary: '#ffc4fc', grid: '#6e286d', mapBackground: '#080108', mapFill: '#390638', mapLine: '#f558f1', mapText: '#ffe5ff', signalGlow: '#fa54f5', signalStroke: '#fc6ef7', signalCore: '#ffeaff', active: '#ffc4fc', traceGlow: '#72fff1', traceStart: '#72fff1', traceMid: '#ffffff', traceEnd: '#72fff1' },
    prism: { name: 'PRISM', accent: '#4befff', bright: '#fff0ff', secondary: '#fa56ef', grid: '#594477', mapBackground: '#050108', mapFill: '#25114b', mapLine: '#4befff', mapText: '#fff0ff', signalGlow: '#4befff', signalStroke: '#fa56ef', signalCore: '#fff7ff', active: '#fa56ef', traceGlow: '#fff37e', traceStart: '#fff37e', traceMid: '#ffffff', traceEnd: '#fff37e' }
  };
  const root = document.documentElement;
  const map = () => typeof state !== 'undefined' ? state.map : null;
  let paletteKey = 'crimson';

  function paint(layer, property, value) {
    try { map()?.setPaintProperty(layer, property, value); } catch (error) { /* Layer is not present in every map style. */ }
  }

  function applyMapPalette() {
    const activeMap = map();
    const palette = palettes[paletteKey];
    if (!activeMap?.loaded()) return;
    for (const layer of activeMap.getStyle().layers || []) {
      if (layer.id.startsWith('pager-')) continue;
      try {
        if (layer.type === 'background') activeMap.setPaintProperty(layer.id, 'background-color', palette.mapBackground);
        if (layer.type === 'line') { activeMap.setPaintProperty(layer.id, 'line-color', palette.mapLine); activeMap.setPaintProperty(layer.id, 'line-opacity', .76); }
        if (layer.type === 'fill') { activeMap.setPaintProperty(layer.id, 'fill-color', palette.mapFill); activeMap.setPaintProperty(layer.id, 'fill-opacity', .2); }
        if (layer.type === 'symbol' && layer.layout?.['text-field']) { activeMap.setPaintProperty(layer.id, 'text-color', palette.mapText); activeMap.setPaintProperty(layer.id, 'text-halo-color', palette.mapBackground); }
      } catch (error) { /* A few style layers intentionally do not expose every property. */ }
    }
    paint('pager-signal-cluster-glow', 'circle-color', palette.signalGlow);
    paint('pager-signal-clusters', 'circle-stroke-color', palette.signalStroke);
    paint('pager-signal-cluster-count', 'text-color', palette.bright);
    paint('pager-signal-halo', 'circle-color', palette.signalGlow);
    paint('pager-signal-core', 'circle-color', palette.signalCore);
    paint('pager-signal-core', 'circle-stroke-color', palette.signalStroke);
    paint('pager-active-signal', 'circle-color', palette.active);
    paint('pager-active-signal', 'circle-stroke-color', palette.bright);
    paint('pager-ssid-trace-glow', 'line-color', palette.traceGlow);
    paint('pager-ssid-trace', 'line-gradient', ['interpolate', ['linear'], ['line-progress'], 0, palette.traceStart, .52, palette.traceMid, 1, palette.traceEnd]);
  }

  function updatePicker() {
    const palette = palettes[paletteKey];
    document.querySelectorAll('.palette-choice').forEach(choice => choice.setAttribute('aria-checked', String(choice.dataset.palette === paletteKey)));
    const name = document.querySelector('#paletteName');
    if (name) name.textContent = palette.name;
  }

  function applyPalette(key, announce = true) {
    if (!palettes[key]) return;
    paletteKey = key;
    root.dataset.palette = key;
    window.NETRIDER_PALETTE = palettes[key];
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', palettes[key].mapBackground);
    try { localStorage.setItem('netrider.palette', key); } catch (error) { /* Palette still works when browser storage is unavailable. */ }
    updatePicker();
    applyMapPalette();
    if (typeof drawCharts === 'function') drawCharts();
    if (announce && typeof toast === 'function') toast(`PALETTE // ${palettes[key].name}`);
  }

  function positionPanel() {
    const toggle = document.querySelector('#paletteToggle');
    const panel = document.querySelector('#palettePanel');
    if (!toggle || !panel) return;
    const toggleRect = toggle.getBoundingClientRect();
    const panelWidth = panel.offsetWidth || 186;
    const panelHeight = panel.offsetHeight || 236;
    const left = Math.max(8, Math.min(window.innerWidth - panelWidth - 8, toggleRect.right - panelWidth));
    const top = Math.min(window.innerHeight - panelHeight - 8, toggleRect.bottom + 8);
    panel.style.left = `${left}px`;
    panel.style.top = `${Math.max(8, top)}px`;
  }

  function setPanel(open) {
    const toggle = document.querySelector('#paletteToggle');
    const panel = document.querySelector('#palettePanel');
    if (!toggle || !panel) return;
    panel.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    if (open) positionPanel();
  }

  try {
    const stored = localStorage.getItem('netrider.palette');
    if (palettes[stored]) paletteKey = stored;
  } catch (error) { /* Crimson remains the default. */ }
  applyPalette(paletteKey, false);

  const activeMap = map();
  if (activeMap?.loaded()) applyMapPalette();
  else activeMap?.on('load', applyMapPalette);

  // The top bar is intentionally clipped into an angled HUD shape. Move the
  // menu out of that clipping context so its choices remain tappable.
  const initialPanel = document.querySelector('#palettePanel');
  if (initialPanel?.parentElement?.classList.contains('palette-dock')) document.body.append(initialPanel);

  document.querySelector('#paletteToggle')?.addEventListener('click', event => {
    event.stopPropagation();
    const panel = document.querySelector('#palettePanel');
    setPanel(Boolean(panel?.hidden));
  });
  document.querySelectorAll('.palette-choice').forEach(choice => choice.addEventListener('click', () => {
    applyPalette(choice.dataset.palette);
    setPanel(false);
  }));
  document.addEventListener('click', event => { if (!event.target.closest('.palette-dock, .palette-panel')) setPanel(false); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') setPanel(false); });
  window.addEventListener('resize', () => { if (!document.querySelector('#palettePanel')?.hidden) positionPanel(); });
  window.addEventListener('scroll', () => { if (!document.querySelector('#palettePanel')?.hidden) positionPanel(); }, { passive: true });
  window.applyNetRiderPalette = applyPalette;
})();

(() => {
  if (!window.NETRIDER_PAGER) return;

  const endpoint = name => `/cgi-bin/${name}.sh`;
  const live = { enabled: false, following: true, initial: false, polling: false, timer: null, lastFile: '', lastPosition: null };
  const library = { files: [], selected: new Set(), signedIn: false, authChecked: false };
  const toggle = $('#liveToggle');
  const follow = $('#followLive');
  const indicator = $('#liveIndicator');
  const status = $('#liveStatus');
  const map = () => state.map;
  const recordKey = record => [record.mac, record.firstSeen, record.lat.toFixed(6), record.lng.toFixed(6), record.rssi, record.channel].join('|');
  const geocoder = window.NETRIDER_GEOCODER;
  const geocodeCache = new Map();
  const centroidTownCache = new Map();
  let geocodeLastRequestAt = 0;

  const geocodeKey = target => `${target.latitude.toFixed(geocoder.cachePrecision)},${target.longitude.toFixed(geocoder.cachePrecision)}`;
  const wait = milliseconds => new Promise(resolve => window.setTimeout(resolve, milliseconds));
  const getCachedPlace = key => {
    if (geocodeCache.has(key)) return geocodeCache.get(key);
    try {
      const cached = sessionStorage.getItem(`netrider.geocode.${key}`);
      if (cached) { const place = JSON.parse(cached); geocodeCache.set(key, place); return place; }
    } catch (error) { console.warn('Geocode cache unavailable:', error); }
    return null;
  };
  const cachePlace = (key, place) => {
    geocodeCache.set(key, place);
    try { sessionStorage.setItem(`netrider.geocode.${key}`, JSON.stringify(place)); } catch (error) { console.warn('Geocode cache write failed:', error); }
  };
  const centroidTownKey = file => `${Number(file.centroid.lat).toFixed(geocoder.cachePrecision)},${Number(file.centroid.lng).toFixed(geocoder.cachePrecision)}`;
  const getCachedCentroidTown = key => {
    if (centroidTownCache.has(key)) return centroidTownCache.get(key);
    try {
      const cached = sessionStorage.getItem(`netrider.centroid-town.${key}`);
      if (cached) { centroidTownCache.set(key, cached); return cached; }
    } catch (error) { console.warn('Centroid town cache unavailable:', error); }
    return null;
  };
  const cacheCentroidTown = (key, town) => {
    centroidTownCache.set(key, town);
    try { sessionStorage.setItem(`netrider.centroid-town.${key}`, town); } catch (error) { console.warn('Centroid town cache write failed:', error); }
  };
  const jsonp = (url, timeoutMs = 9000) => new Promise((resolve, reject) => {
    const callback = `netriderNominatim${Date.now()}${Math.random().toString(36).slice(2)}`;
    const script = document.createElement('script');
    const cleanup = () => { window.clearTimeout(timeout); script.remove(); try { delete window[callback]; } catch (error) { window[callback] = undefined; } };
    const timeout = window.setTimeout(() => { cleanup(); reject(Error('REQUEST TIMEOUT')); }, timeoutMs);
    window[callback] = result => { cleanup(); resolve(result); };
    script.async = true;
    script.referrerPolicy = 'strict-origin-when-cross-origin';
    script.onerror = () => { cleanup(); reject(Error('NETWORK REQUEST BLOCKED')); };
    url.searchParams.set('json_callback', callback);
    script.src = url.toString();
    document.head.append(script);
  });
  const normalizePlace = (result, target) => {
    const address = result.address || {};
    const street = [address.house_number, address.road || address.pedestrian || address.footway].filter(Boolean).join(' ');
    const locality = [address.neighbourhood || address.suburb, address.city || address.town || address.village || address.municipality, address.state].filter(Boolean).join(' · ');
    return {
      name: result.name || result.namedetails?.name || target.local.name || result.display_name?.split(',')[0] || null,
      address: street || target.local.address || null,
      type: [result.category, result.type].filter(Boolean).join(' / ') || target.local.type || null,
      locality: locality || null,
      found: Boolean(result.place_id || result.osm_id)
    };
  };
  const nearestTown = result => {
    const address = result?.address || {};
    const locality = address.city || address.town || address.village || address.hamlet || address.municipality || address.county;
    const region = address.state || address.region || address.country;
    return [locality, region].filter(Boolean).join(' // ') || null;
  };
  async function lookupOnlinePlace() {
    const target = state.placeTarget;
    if (!target || !geocoder?.reverseEndpoint) return;
    const requestId = ++state.placeRequest;
    const key = geocodeKey(target);
    const cached = getCachedPlace(key);
    if (cached) {
      setPlaceInspector({ ...cached, message: 'ONLINE ADDRESS LOOKUP // CACHED ON THIS DEVICE.' }, 'READY');
      return;
    }
    setPlaceInspector({ ...target.local, message: 'ONLINE LOOKUP // REQUESTING ADDRESS DATA…' }, 'LOOKUP', true);
    const remaining = geocodeLastRequestAt + geocoder.minimumIntervalMs - Date.now();
    if (remaining > 0) await wait(remaining);
    if (requestId !== state.placeRequest) return;
    geocodeLastRequestAt = Date.now();
    try {
      const url = new URL(geocoder.reverseEndpoint);
      url.search = new URLSearchParams({ format: 'jsonv2', lat: target.latitude.toFixed(6), lon: target.longitude.toFixed(6), zoom: '18', addressdetails: '1', namedetails: '1', extratags: '1', layer: 'address,poi' });
      const result = await jsonp(url);
      if (result.error) throw Error(result.error);
      if (requestId !== state.placeRequest) return;
      const place = normalizePlace(result, target);
      if (!place.found) throw Error('NO RESULT');
      cachePlace(key, place);
      setPlaceInspector({ ...place, message: 'ONLINE OPENSTREETMAP PLACE DATA // VERIFIED.' }, 'READY');
    } catch (error) {
      if (requestId !== state.placeRequest) return;
      console.warn('Online place lookup failed:', error);
      setPlaceInspector({ ...target.local, lookup: true, message: 'ONLINE LOOKUP UNAVAILABLE // CHECK CELLULAR DATA.' }, 'MAP');
    }
  }

  function applyGreenMapPalette() {
    if (!map()?.loaded()) return;
    for (const layer of map().getStyle().layers) {
      if (layer.id.startsWith('pager-')) continue;
      try {
        if (layer.type === 'line') { map().setPaintProperty(layer.id, 'line-color', '#78ff63'); map().setPaintProperty(layer.id, 'line-opacity', .78); }
        if (layer.type === 'fill') { map().setPaintProperty(layer.id, 'fill-color', '#0c2a10'); map().setPaintProperty(layer.id, 'fill-opacity', .18); }
        if (layer.type === 'symbol' && layer.layout?.['text-field']) { map().setPaintProperty(layer.id, 'text-color', '#caffb9'); map().setPaintProperty(layer.id, 'text-halo-color', '#020603'); }
      } catch (error) { console.warn('Map palette layer skipped:', layer.id, error); }
    }
    const colors = [
      ['pager-signal-cluster-glow', 'circle-color', '#8dff78'],
      ['pager-signal-clusters', 'circle-stroke-color', '#8dff78'],
      ['pager-signal-cluster-count', 'text-color', '#e4ffdb'],
      ['pager-signal-halo', 'circle-color', '#8dff78'],
      ['pager-signal-core', 'circle-color', '#d5ffcb'],
      ['pager-signal-core', 'circle-stroke-color', '#3fba4a']
    ];
    colors.forEach(([layer, property, color]) => { try { map().setPaintProperty(layer, property, color); } catch (error) { console.warn('Signal palette layer skipped:', layer, error); } });
  }

  function ui(message, level = 'STANDBY') {
    indicator.textContent = level;
    indicator.dataset.level = level.toLowerCase();
    status.textContent = message;
    toggle.textContent = live.enabled ? 'STOP LIVE' : 'START LIVE';
    follow.disabled = !live.initial;
    follow.querySelector('b').textContent = live.following && live.initial ? 'FOLLOWING' : 'FOLLOW LIVE';
    follow.title = live.following && live.initial ? 'Following the newest WiGLE-log coordinate' : 'Follow the newest WiGLE-log coordinate';
    follow.setAttribute('aria-pressed', String(live.following && live.initial));
    follow.classList.toggle('active', live.following && live.initial);
  }

  function latestPosition(records) {
    // WiGLE appends observations to the CSV. The final geolocated row is
    // therefore the Pager's current position, even if its AP was seen before.
    for (let index = records.length - 1; index >= 0; index--) {
      const record = records[index];
      if (Number.isFinite(record?.lat) && Number.isFinite(record?.lng)) return record;
    }
    return null;
  }

  function followLatestPosition() {
    if (!live.following || !live.lastPosition || !map()?.loaded()) return;
    const location = [live.lastPosition.lng, live.lastPosition.lat];
    const zoom = Math.max(map().getZoom(), 15.8);
    // Recenter on every live poll. This is intentionally independent of new
    // AP records and marker-change thresholds, so the viewport tracks the
    // latest WiGLE coordinate continuously while follow is armed.
    map().jumpTo({ center: location, zoom });
  }

  function setDeviceMarker(signal) {
    if (!signal || !Number.isFinite(signal.lat) || !Number.isFinite(signal.lng)) return;
    live.lastPosition = { lat: signal.lat, lng: signal.lng };
    if (!map()?.loaded()) return;
    const location = [signal.lng, signal.lat];
    if (state.deviceMarker) state.deviceMarker.setLngLat(location);
    else {
      const marker = document.createElement('div');
      marker.className = 'device-marker live-device-marker';
      marker.title = 'Latest WiGLE GPS coordinate';
      state.deviceMarker = new maplibregl.Marker({ element: marker, anchor: 'center' }).setLngLat(location).addTo(map());
    }
    $('#coordinates').textContent = `LIVE GPS ${Math.abs(signal.lat).toFixed(5)}° ${signal.lat < 0 ? 'S' : 'N'} · ${Math.abs(signal.lng).toFixed(5)}° ${signal.lng < 0 ? 'W' : 'E'}`;
  }

  function merge(records, filename) {
    if (!records.length) return;
    if (!live.initial) {
      live.initial = true;
      applyDataset(records, 'PAGER LIVE');
      ui(`${filename || 'ACTIVE WiGLE LOG'} // ${records.length} GEOLOCATED SIGNALS`, 'LIVE');
    } else {
      const known = new Set(state.records.map(recordKey));
      const additions = records.filter(record => !known.has(recordKey(record)));
      if (additions.length) {
        const selectedKey = state.selected && recordKey(state.selected);
        state.records = state.records.concat(additions).slice(-1500);
        state.records.forEach((record, index) => { record._index = index; });
        state.selected = state.records.find(record => recordKey(record) === selectedKey) || null;
        apply();
        ui(`${filename || 'ACTIVE WiGLE LOG'} // +${additions.length} NEW // ${state.records.length} IN VIEW`, 'LIVE');
      } else ui(`${filename || 'ACTIVE WiGLE LOG'} // WATCHING FOR NEW OBSERVATIONS`, 'LIVE');
    }
    setDeviceMarker(latestPosition(records));
  }

  async function poll() {
    if (!live.enabled || live.polling) return;
    live.polling = true;
    try {
      const response = await fetch(`${endpoint('live')}?t=${Date.now()}`, { cache: 'no-store' });
      if (response.status === 204) {
        ui('WAITING FOR AN ACTIVE WiGLE LOG AND GPS FIX.', 'WAITING');
        return;
      }
      if (!response.ok) throw Error(`REQUEST ${response.status}`);
      const filename = response.headers.get('X-NetRider-File') || 'ACTIVE WiGLE LOG';
      const records = parseWigle(await response.text());
      if (live.lastFile && live.lastFile !== filename) {
        live.initial = false;
        live.lastPosition = null;
        toast(`NEW LIVE SESSION // ${filename}`);
      }
      live.lastFile = filename;
      merge(records, filename);
      followLatestPosition();
    } catch (error) {
      console.warn('Pager live feed failed:', error);
      ui(`LIVE FEED UNAVAILABLE // ${error.message || 'RETRYING'}`, 'OFFLINE');
    } finally {
      live.polling = false;
    }
  }

  function start() {
    if (live.enabled) return;
    live.enabled = true;
    live.following = true;
    ui('CONNECTING TO THE ACTIVE PAGER WiGLE LOG…', 'CONNECTING');
    poll();
    live.timer = window.setInterval(poll, 1800);
  }

  function stop() {
    live.enabled = false;
    window.clearInterval(live.timer);
    live.timer = null;
    ui(live.initial ? 'LIVE FEED PAUSED. CURRENT MAP DATA RETAINED.' : 'LIVE FEED STOPPED.', 'PAUSED');
  }

  const selectorModal = $('#logSelectorModal');
  const selectorList = $('#logSelectorList');
  const selectorStatus = $('#logSelectorStatus');
  const selectorSelection = $('#logSelectorSelection');
  const selectorEstimate = $('#logSelectorEstimate');
  const selectorDisplay = $('#logSelectorDisplay');
  const selectorUpload = $('#logSelectorUpload');
  const selectorDelete = $('#logSelectorDelete');
  const authState = $('#wigleAuthState');
  const signIn = $('#wigleSignIn');
  const credentials = $('#wigleCredentials');

  const formatBytes = bytes => {
    const value = Number(bytes) || 0;
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(value < 10240 ? 1 : 0)} KB`;
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  };
  const formatCount = value => new Intl.NumberFormat().format(Number(value) || 0);
  const formatCaptureTime = value => {
    if (!value) return 'DATE UNKNOWN';
    const date = new Date(String(value).replace(' ', 'T'));
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
  };
  const formatLoggedTime = value => {
    const date = new Date(Number(value) * 1000);
    if (!value || Number.isNaN(date.getTime())) return 'LOGGED TIME UNKNOWN';
    return `LOGGED ${date.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })}`;
  };
  const captureRange = file => {
    if (!file.firstSeen) return formatLoggedTime(file.modified);
    const first = formatCaptureTime(file.firstSeen);
    const last = file.lastSeen && file.lastSeen !== file.firstSeen ? ` → ${formatCaptureTime(file.lastSeen)}` : '';
    return `${first}${last}`;
  };
  const selectedFiles = () => library.files.filter(file => library.selected.has(file.id));
  const setSelectorStatus = (message, level = 'info') => { selectorStatus.textContent = message; selectorStatus.dataset.level = level; };
  const secureDashboard = () => location.protocol === 'https:' && window.isSecureContext;

  function updateLibrarySelection() {
    const files = selectedFiles();
    const lineCount = files.reduce((sum, file) => sum + (Number(file.lines) || 0), 0);
    const metadataPending = files.some(file => file.metadataLoading);
    const hasMappableLog = files.some(file => !file.metadataLoaded || Number(file.lines) > 0);
    selectorSelection.textContent = `${files.length} LOG${files.length === 1 ? '' : 'S'} SELECTED`;
    selectorEstimate.textContent = `${formatCount(lineCount)} ${metadataPending ? 'LINES // ANALYZING' : 'LINES ESTIMATED'}`;
    selectorDisplay.disabled = !files.length || metadataPending || !hasMappableLog;
    selectorUpload.disabled = !files.length || metadataPending || !hasMappableLog;
    selectorDelete.disabled = !files.length || metadataPending;
    $('#logSelectorAll').textContent = library.files.length && files.length === library.files.length ? 'UNSELECT ALL' : 'SELECT ALL';
  }

  async function lookupCentroidTown(file) {
    if (!geocoder?.reverseEndpoint || !file?.centroid || file.centroidTownLoading || file.centroidTown || file.centroidTownUnavailable) return;
    const latitude = Number(file.centroid.lat);
    const longitude = Number(file.centroid.lng);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return;
    const key = centroidTownKey(file);
    const cached = getCachedCentroidTown(key);
    if (cached) {
      file.centroidTown = cached;
      renderLogOptions();
      return;
    }
    file.centroidTownLoading = true;
    renderLogOptions();
    const remaining = geocodeLastRequestAt + geocoder.minimumIntervalMs - Date.now();
    if (remaining > 0) await wait(remaining);
    geocodeLastRequestAt = Date.now();
    try {
      const url = new URL(geocoder.reverseEndpoint);
      // Zoom 10 is intentionally town-scale rather than a street/building lookup.
      url.search = new URLSearchParams({ format: 'jsonv2', lat: latitude.toFixed(6), lon: longitude.toFixed(6), zoom: '10', addressdetails: '1' });
      const result = await jsonp(url);
      const town = nearestTown(result);
      if (!town) throw Error('NO TOWN RESULT');
      cacheCentroidTown(key, town);
      file.centroidTown = town;
    } catch (error) {
      console.warn('Centroid town lookup failed:', error);
      file.centroidTownUnavailable = true;
    } finally {
      file.centroidTownLoading = false;
      if (!selectorModal.hidden) renderLogOptions();
    }
  }

  function renderLibrarySummary() {
    const box = $('#captureLibrary');
    if (!library.files.length) {
      box.innerHTML = '<small>No WiGLE CSVs found on this Pager yet.</small>';
      return;
    }
    const lineCount = library.files.reduce((sum, file) => sum + (Number(file.lines) || 0), 0);
    box.innerHTML = `<button class="library-summary" type="button"><b>${library.files.length} CAPTURE LOG${library.files.length === 1 ? '' : 'S'} AVAILABLE</b><small>${formatCount(lineCount)} LINES ESTIMATED // OPEN LOGS TO SELECT</small></button>`;
    box.querySelector('.library-summary').onclick = openLogSelector;
  }

  async function hydrateFileMetadata(file) {
    if (!file || file.metadataLoading || file.metadataLoaded) return;
    file.metadataLoading = true;
    renderLogOptions();
    setSelectorStatus(`ANALYZING ${file.name} FOR EXACT LINE COUNT, CAPTURE RANGE, AND GPS CENTROID…`);
    try {
      const response = await fetch(`${endpoint('capture-meta')}?file=${encodeURIComponent(file.id)}`, { cache: 'no-store' });
      const detail = await response.json().catch(() => ({}));
      if (!response.ok || !detail.ok) throw Error(detail.message || `REQUEST ${response.status}`);
      Object.assign(file, detail, { metadataLoaded: true, metadataLoading: false });
      setSelectorStatus(Number(file.lines) > 0 ? `METADATA READY // ${file.name}` : `EMPTY WiGLE LOG // ${file.name} HAS NO OBSERVATIONS TO DISPLAY OR UPLOAD.`, Number(file.lines) > 0 ? 'success' : 'error');
      lookupCentroidTown(file);
    } catch (error) {
      file.metadataLoading = false;
      console.warn('Pager capture metadata failed:', error);
      setSelectorStatus(`METADATA UNAVAILABLE // ${file.name} // ${error.message || 'RETRY'}`, 'error');
    }
    renderLogOptions();
    renderLibrarySummary();
  }

  function renderLogOptions() {
    if (!library.files.length) {
      selectorList.innerHTML = '<small>No WiGLE CSVs found on this Pager yet.</small>';
      updateLibrarySelection();
      return;
    }
    selectorList.innerHTML = library.files.map(file => {
      const centroid = file.centroidTown
        ? file.centroidTown
        : file.centroidTownLoading ? 'LOCATING TOWN…'
          : file.centroidTownUnavailable ? 'TOWN LOOKUP UNAVAILABLE'
            : file.centroid && Number.isFinite(Number(file.centroid.lat)) && Number.isFinite(Number(file.centroid.lng))
              ? 'LOCATE ON SELECT'
              : file.metadataLoading ? 'ANALYZING GPS…' : 'ANALYZE ON SELECT';
      const checked = library.selected.has(file.id) ? ' checked' : '';
      const lineLabel = file.estimated ? 'EST. LINES' : 'LINES';
      return `<label class="log-option"><input type="checkbox" data-log-id="${esc(file.id)}"${checked}/><span class="log-check">✓</span><span class="log-name"><b>${esc(file.name)}</b><small>${formatBytes(file.size)} // ${formatCount(file.lines)} ${lineLabel}</small></span><span class="log-meta"><span>CAPTURED / LOGGED</span><b>${esc(captureRange(file))}</b></span><span class="log-centroid"><span>NEAREST TOWN</span><b>${esc(centroid)}</b></span></label>`;
    }).join('');
    selectorList.querySelectorAll('input[data-log-id]').forEach(input => {
      input.onchange = () => {
        const file = library.files.find(item => item.id === input.dataset.logId);
        if (input.checked) {
          library.selected.add(input.dataset.logId);
          hydrateFileMetadata(file);
          lookupCentroidTown(file);
        } else library.selected.delete(input.dataset.logId);
        updateLibrarySelection();
      };
    });
    updateLibrarySelection();
  }

  async function refreshWigleAuth() {
    authState.textContent = 'CHECKING…';
    authState.dataset.state = 'checking';
    try {
      const response = await fetch(endpoint('wigle-auth'), { cache: 'no-store' });
      if (!response.ok) throw Error(`REQUEST ${response.status}`);
      const result = await response.json();
      library.signedIn = Boolean(result.configured);
      library.authChecked = true;
      authState.textContent = library.signedIn ? 'PAGER TOKEN READY' : 'LOG-IN REQUIRED';
      authState.dataset.state = library.signedIn ? 'ready' : 'error';
      signIn.textContent = library.signedIn ? 'LOGGED IN' : 'LOG IN';
      signIn.title = library.signedIn ? 'Pager WiGLE upload token is ready' : 'Log in to WiGLE on this Pager';
      signIn.classList.remove('secondary');
      if (library.signedIn) credentials.hidden = true;
    } catch (error) {
      library.signedIn = false;
      library.authChecked = false;
      authState.textContent = 'STATUS UNAVAILABLE';
      authState.dataset.state = 'error';
      signIn.textContent = 'RETRY STATUS';
    }
  }

  async function loadPagerCatalog() {
    const box = $('#captureLibrary');
    box.innerHTML = '<small>Scanning Pager WiGLE loot…</small>';
    try {
      const response = await fetch(endpoint('captures'), { cache: 'no-store' });
      if (!response.ok) throw Error(`REQUEST ${response.status}`);
      const files = await response.json();
      files.forEach(file => { file.metadataLoaded = file.estimated === false; });
      const validIds = new Set(files.map(file => file.id));
      library.selected = new Set([...library.selected].filter(id => validIds.has(id)));
      library.files = files;
      renderLibrarySummary();
      if (!selectorModal.hidden) renderLogOptions();
    } catch (error) {
      box.innerHTML = '<small>Pager WiGLE library unavailable.</small>';
      if (!selectorModal.hidden) {
        selectorList.innerHTML = '<small>Pager WiGLE library unavailable. Refresh to retry.</small>';
        setSelectorStatus(`CATALOGUE REQUEST FAILED // ${error.message || 'RETRY'}`, 'error');
      }
    }
  }

  async function openLogSelector() {
    selectorModal.hidden = false;
    credentials.hidden = true;
    setSelectorStatus('LOADING PAGER WiGLE LOG METADATA…');
    await Promise.all([loadPagerCatalog(), refreshWigleAuth()]);
    if (library.files.length) setSelectorStatus('SELECT ONE OR MORE LOGS TO DISPLAY TOGETHER OR UPLOAD TO WiGLE.', 'success');
  }

  function closeLogSelector() {
    credentials.reset();
    credentials.hidden = true;
    selectorModal.hidden = true;
  }

  async function displaySelectedLogs() {
    const files = selectedFiles();
    if (!files.length) return;
    if (files.some(file => file.metadataLoading)) {
      setSelectorStatus('WAIT FOR SELECTED LOG METADATA BEFORE DISPLAYING THE MAP.');
      return;
    }
    const mappableFiles = files.filter(file => !file.metadataLoaded || Number(file.lines) > 0);
    if (!mappableFiles.length) {
      setSelectorStatus('SELECTED LOGS HAVE NO WiGLE OBSERVATIONS TO DISPLAY ON THE MAP.', 'error');
      return;
    }
    selectorDisplay.disabled = true;
    setSelectorStatus(`LOADING ${mappableFiles.length} SELECTED WiGLE LOG${mappableFiles.length === 1 ? '' : 'S'} ON THE MAP…`);
    try {
      const datasets = await Promise.all(mappableFiles.map(async file => {
        const response = await fetch(`${endpoint('capture')}?file=${encodeURIComponent(file.id)}`, { cache: 'no-store' });
        if (!response.ok) throw Error(`${file.name}: REQUEST ${response.status}`);
        return parseWigle(await response.text());
      }));
      const records = datasets.flat();
      if (!records.length) throw Error('NO GEOLOCATED SIGNALS');
      live.initial = false;
      applyDataset(records, `PAGER LOOT // ${mappableFiles.length} LOGS`);
      closeLogSelector();
      toast(`${records.length} GEOLOCATED SIGNALS // ${mappableFiles.length} LOGS DISPLAYED ON MAP`);
    } catch (error) {
      console.warn('Pager multi-log load failed:', error);
      setSelectorStatus(`UNABLE TO DISPLAY SELECTION // ${error.message || 'UNKNOWN ERROR'}`, 'error');
    } finally {
      updateLibrarySelection();
    }
  }

  async function submitWigleCredentials(event) {
    event.preventDefault();
    if (!secureDashboard()) {
      setSelectorStatus('SIGN-IN REQUIRES THE SECURE HTTPS DASHBOARD. OPEN THE HTTPS ADDRESS SHOWN BY THE PAGER PAYLOAD.', 'error');
      return;
    }
    const username = $('#wigleUsername').value;
    const password = $('#wiglePassword').value;
    if (!username || !password) return;
    $('#wigleSubmit').disabled = true;
    setSelectorStatus('CONTACTING WiGLE TO OBTAIN THE PAGER UPLOAD TOKEN…');
    try {
      const body = new URLSearchParams({ username, password });
      const response = await fetch(endpoint('wigle-auth'), { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' }, body, cache: 'no-store' });
      const result = await response.json().catch(() => ({}));
      credentials.reset();
      if (!response.ok || !result.ok) throw Error(result.message || 'SIGN-IN FAILED');
      credentials.hidden = true;
      setSelectorStatus('WiGLE LOG-IN COMPLETE // PAGER UPLOAD TOKEN READY.', 'success');
      await refreshWigleAuth();
    } catch (error) {
      credentials.reset();
      setSelectorStatus(`WiGLE LOG-IN FAILED // ${error.message || 'CHECK CREDENTIALS OR PAGER INTERNET'}`, 'error');
    } finally {
      $('#wigleSubmit').disabled = false;
    }
  }

  async function uploadSelectedLogs() {
    const files = selectedFiles();
    if (!files.length) return;
    if (!secureDashboard()) {
      setSelectorStatus('UPLOAD REQUIRES THE SECURE HTTPS DASHBOARD. OPEN THE HTTPS ADDRESS SHOWN BY THE PAGER PAYLOAD.', 'error');
      return;
    }
    if (!library.signedIn) {
      credentials.hidden = false;
      $('#wigleUsername').focus();
      setSelectorStatus('LOG IN TO WiGLE BEFORE UPLOADING THE SELECTED LOGS.');
      return;
    }
    selectorUpload.disabled = true;
    setSelectorStatus(`UPLOADING ${files.length} SELECTED LOG${files.length === 1 ? '' : 'S'} FROM THE PAGER…`);
    try {
      const body = new URLSearchParams();
      files.forEach(file => body.append('file', file.id));
      const response = await fetch(endpoint('wigle-upload'), { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' }, body, cache: 'no-store' });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result.ok) throw Error(result.message || 'UPLOAD FAILED');
      const complete = Number(result.uploaded) || 0;
      const total = Number(result.total) || files.length;
      setSelectorStatus(`${complete}/${total} LOG${total === 1 ? '' : 'S'} UPLOADED TO WiGLE. ${complete === total ? 'THE SELECTED FILES REMAIN ON THE PAGER.' : 'CHECK THE PAGER INTERNET CONNECTION OR WiGLE TOKEN.'}`, complete === total ? 'success' : 'error');
      if (complete !== total) await refreshWigleAuth();
    } catch (error) {
      setSelectorStatus(`WiGLE UPLOAD FAILED // ${error.message || 'CHECK PAGER INTERNET'}`, 'error');
      await refreshWigleAuth();
    } finally {
      updateLibrarySelection();
    }
  }

  async function deleteSelectedLogs() {
    const files = selectedFiles();
    if (!files.length) return;
    const noun = files.length === 1 ? 'WiGLE CSV' : 'WiGLE CSVs';
    const confirmation = files.length === 1
      ? `Delete ${files[0].name} from Pager loot?\n\nThis permanently deletes the selected ${noun}.`
      : `Delete ${files.length} selected ${noun} from Pager loot?\n\nThis permanently deletes the selected files.`;
    if (!window.confirm(confirmation)) {
      setSelectorStatus('DELETE CANCELLED.');
      return;
    }
    if (!secureDashboard()) {
      setSelectorStatus('DELETE REQUIRES THE SECURE HTTPS DASHBOARD.', 'error');
      return;
    }
    selectorDelete.disabled = true;
    setSelectorStatus(`DELETING ${files.length} SELECTED ${noun.toUpperCase()} FROM PAGER LOOT…`);
    try {
      const body = new URLSearchParams({ confirm: 'DELETE' });
      files.forEach(file => body.append('file', file.id));
      const response = await fetch(endpoint('delete-captures'), { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' }, body, cache: 'no-store' });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result.ok) throw Error(result.message || 'DELETE FAILED');
      const deleted = Number(result.deleted) || 0;
      const total = Number(result.total) || files.length;
      library.selected.clear();
      await loadPagerCatalog();
      setSelectorStatus(`${deleted}/${total} ${noun.toUpperCase()} DELETED FROM PAGER LOOT.`, deleted === total ? 'success' : 'error');
    } catch (error) {
      console.warn('Pager capture delete failed:', error);
      setSelectorStatus(`UNABLE TO DELETE SELECTION // ${error.message || 'UNKNOWN ERROR'}`, 'error');
    } finally {
      updateLibrarySelection();
    }
  }

  toggle.addEventListener('click', () => live.enabled ? stop() : start());
  follow.addEventListener('click', () => { live.following = !live.following; ui(live.following ? 'FOLLOWING NEWEST WiGLE COORDINATE.' : 'LIVE FOLLOW PAUSED.', live.initial ? 'LIVE' : 'STANDBY'); if (live.following) followLatestPosition(); });
  $('#refreshLibrary').onclick = loadPagerCatalog;
  $('#logSelectorOpen').onclick = openLogSelector;
  $('#logSelectorClose').onclick = closeLogSelector;
  selectorModal.querySelector('[data-log-selector-close]').onclick = closeLogSelector;
  $('#logSelectorRefresh').onclick = async () => { setSelectorStatus('REFRESHING PAGER WiGLE LOG METADATA…'); await Promise.all([loadPagerCatalog(), refreshWigleAuth()]); if (library.files.length) setSelectorStatus('PAGER WiGLE LOG METADATA REFRESHED.', 'success'); };
  $('#logSelectorAll').onclick = () => { if (library.selected.size === library.files.length) library.selected.clear(); else library.files.forEach(file => library.selected.add(file.id)); renderLogOptions(); };
  $('#logSelectorClear').onclick = () => { library.selected.clear(); renderLogOptions(); };
  $('#logSelectorDelete').onclick = deleteSelectedLogs;
  $('#logSelectorDisplay').onclick = displaySelectedLogs;
  $('#logSelectorUpload').onclick = uploadSelectedLogs;
  signIn.onclick = () => { if (library.signedIn) { credentials.hidden = true; setSelectorStatus('PAGER WiGLE UPLOAD TOKEN IS READY.', 'success'); return; } credentials.hidden = false; $('#wigleUsername').focus(); setSelectorStatus('LOG IN TO CREATE THE PAGER WiGLE UPLOAD TOKEN.'); };
  $('#wigleCancel').onclick = () => { credentials.reset(); credentials.hidden = true; setSelectorStatus('WiGLE SIGN-IN CANCELLED.'); };
  credentials.addEventListener('submit', submitWigleCredentials);
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !selectorModal.hidden) closeLogSelector(); });
  if (geocoder?.reverseEndpoint) {
    lookupSelectedPlace = lookupOnlinePlace;
    window.lookupSelectedPlace = lookupOnlinePlace;
    $('.place-attribution').textContent = 'ONLINE LOOKUP SENDS THE SELECTED COORDINATE TO OPENSTREETMAP';
  }
  if (map()?.loaded()) applyGreenMapPalette(); else map()?.on('load', applyGreenMapPalette);
  map()?.on('load', () => { if (live.lastPosition) { setDeviceMarker(live.lastPosition); followLatestPosition(); } });
  map()?.on('dragstart', () => { if (live.following) { live.following = false; ui('LIVE FOLLOW PAUSED AFTER MAP PAN.', live.initial ? 'LIVE' : 'STANDBY'); } });
  document.addEventListener('visibilitychange', () => { if (document.hidden) return; if (live.enabled) poll(); });
  ui('PAGER LIVE FEED READY. START TO FOLLOW THE ACTIVE WiGLE LOG.');
  loadPagerCatalog();
  if (window.NETRIDER_LIVE_AUTOSTART) start();
})();

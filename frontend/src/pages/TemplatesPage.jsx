import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { FaLayerGroup } from 'react-icons/fa';
import { normalizeRamInput } from '../utils/ram';

export default function TemplatesPage({ API, authHeaders }) {
  const safeAuthHeaders = useMemo(() => (typeof authHeaders === 'function' ? authHeaders : () => ({})), [authHeaders]);
  const numberFormatter = useMemo(() => new Intl.NumberFormat(), []);

  const [serverName, setServerName] = useState('mp-' + Math.random().toString(36).slice(2, 6));
  const [hostPort, setHostPort] = useState('');
  const [minRam, setMinRam] = useState('2048M');
  const [maxRam, setMaxRam] = useState('4096M');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const [zipFile, setZipFile] = useState(null);
  const [javaOverride, setJavaOverride] = useState('');
  const [serverType, setServerType] = useState('');
  const [serverVersion, setServerVersion] = useState('');

  const [providers, setProviders] = useState([{ id: 'modrinth', name: 'Modrinth' }]);
  const [provider, setProvider] = useState('all');
  const [catalogQuery, setCatalogQuery] = useState('');
  const [catalogLoader, setCatalogLoader] = useState('');
  const [catalogMC, setCatalogMC] = useState('');
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState('');
  const [catalogResults, setCatalogResults] = useState([]);
  const [catalogPage, setCatalogPage] = useState(1);
  const CATALOG_PAGE_SIZE = 24;

  const [curatedItems, setCuratedItems] = useState([]);
  const [curatedLoading, setCuratedLoading] = useState(false);
  const [curatedError, setCuratedError] = useState('');

  const [installOpen, setInstallOpen] = useState(false);
  const [installPack, setInstallPack] = useState(null);
  const [installProvider, setInstallProvider] = useState('modrinth');
  const [installVersions, setInstallVersions] = useState([]);
  const [installVersionId, setInstallVersionId] = useState('');
  const [installEvents, setInstallEvents] = useState([]);
  const [installWorking, setInstallWorking] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function loadProviders() {
      try {
        const response = await fetch(`${API}/catalog/providers`);
        const data = await response.json();
        if (!cancelled && Array.isArray(data?.providers)) {
          setProviders(data.providers);
        }
      } catch {
        // Silently ignore provider lookup failures; UI will fallback to defaults
      }
    }
    loadProviders();
    return () => {
      cancelled = true;
    };
  }, [API]);

  const refreshCurated = useCallback(async (opts = {}) => {
    const { signal } = opts;
    setCuratedLoading(true);
    setCuratedError('');
    try {
      const headers = safeAuthHeaders();
      const response = await fetch(`${API}/catalog/curated`, { headers, signal });
      const data = await response.json().catch(() => ({}));
      if (signal?.aborted) return;
      if (!response.ok) {
        setCuratedError(data?.detail || `HTTP ${response.status}`);
        setCuratedItems([]);
        return;
      }
      const templates = Array.isArray(data?.templates) ? data.templates : [];
      setCuratedItems(templates);
    } catch (error) {
      if (signal?.aborted) return;
      setCuratedError(String(error?.message || error));
      setCuratedItems([]);
    } finally {
      if (signal?.aborted) return;
      setCuratedLoading(false);
    }
  }, [API, safeAuthHeaders]);

  useEffect(() => {
    const controller = new AbortController();
    refreshCurated({ signal: controller.signal });
    return () => controller.abort();
  }, [refreshCurated]);

  async function searchCatalog() {
    setCatalogLoading(true);
    setCatalogError('');
    try {
      const params = new URLSearchParams();
      if (catalogQuery) params.set('q', catalogQuery);
      if (catalogLoader) params.set('loader', catalogLoader);
      if (catalogMC) params.set('mc_version', catalogMC);
      params.set('provider', provider);
      params.set('page', String(catalogPage));
      params.set('page_size', String(CATALOG_PAGE_SIZE));
      const response = await fetch(`${API}/catalog/search?${params.toString()}`);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const message = data?.detail || `HTTP ${response.status}`;
        setCatalogError(message);
        setCatalogResults([]);
        return;
      }
      setCatalogResults(Array.isArray(data?.results) ? data.results : []);
    } catch (error) {
      setCatalogError(String(error.message || error));
    } finally {
      setCatalogLoading(false);
    }
  }

  async function openInstallFromCatalog(pack, options = {}) {
    const {
      providerOverride,
      versionOverride,
      recommendedRam,
      suggestedName,
    } = options || {};

    if (suggestedName) {
      setServerName(suggestedName);
    }
    if (recommendedRam && recommendedRam.min) {
      setMinRam(recommendedRam.min);
    }
    if (recommendedRam && recommendedRam.max) {
      setMaxRam(recommendedRam.max);
    }

    setInstallPack(pack);
    setInstallOpen(true);
    setInstallEvents([]);
    setInstallWorking(false);
    try {
      const chosenProvider = providerOverride || (provider === 'all' ? (pack.provider || 'modrinth') : provider);
      setInstallProvider(chosenProvider);
      const packIdentifier = pack.id || pack.slug || pack.project_id || pack.projectSlug;
      if (!packIdentifier) {
        throw new Error('Missing pack identifier');
      }
      const response = await fetch(
        `${API}/catalog/${chosenProvider}/packs/${encodeURIComponent(String(packIdentifier))}/versions`,
        { headers: safeAuthHeaders() }
      );
      const data = await response.json().catch(() => ({}));
      const versions = Array.isArray(data?.versions) ? data.versions : [];
      setInstallVersions(versions);
      if (versionOverride) {
        const match = versions.find(v => String(v.id) === String(versionOverride));
        setInstallVersionId(match ? String(match.id) : (versions[0]?.id || ''));
      } else {
        setInstallVersionId(versions[0]?.id || '');
      }
    } catch (error) {
      setInstallVersions([]);
      setInstallVersionId('');
      setInstallEvents(prev => [...prev, { type: 'error', message: String(error?.message || error) }]);
    }
  }

  async function openCuratedInstall(entry) {
    if (!entry || !entry.install || !entry.install.pack_id) {
      setMsg('Curated template is missing install metadata.');
      return;
    }

    const availabilityKey = String(entry.availability || 'unknown').toLowerCase();
    const blockedStatuses = new Set(['provider-unavailable', 'missing-pack', 'invalid-metadata', 'missing-version', 'error']);
    if (blockedStatuses.has(availabilityKey)) {
      setMsg(entry.availability_message || 'This curated template cannot be installed right now.');
      return;
    }

    setMsg('');

    const installMeta = entry.install;
    const providerOverride = installMeta.provider || entry.provider || 'modrinth';
    const baseName = entry.name || entry.id || serverName;
    const slug = String(baseName)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 18);
    const suggestedName = slug ? `mp-${slug}` : serverName;
    const pseudoPack = {
      id: installMeta.pack_id,
      slug: installMeta.pack_id,
      provider: providerOverride,
      name: entry.name,
      description: entry.short_description || entry.description || '',
      icon_url: entry.icon_url,
      categories: entry.tags || [],
    };

    await openInstallFromCatalog(pseudoPack, {
      providerOverride,
      versionOverride: installMeta.version_id || null,
      recommendedRam: entry.recommended_ram || null,
      suggestedName,
    });

    if (availabilityKey === 'latest-used' && entry.availability_message) {
      setInstallEvents(prev => [...prev, { type: 'info', message: entry.availability_message }]);
    }
  }

  async function submitInstall() {
    if (!installPack) return;
    if (!serverName || !String(serverName).trim()) {
      setInstallEvents(prev => [...prev, { type: 'error', message: 'Server name is required' }]);
      return;
    }
    setInstallWorking(true);
    setInstallEvents([{ type: 'progress', message: 'Submitting install task...' }]);
    try {
      const body = {
        provider: installProvider || (provider === 'all' ? installPack?.provider || 'modrinth' : provider),
        pack_id: String(installPack.id || installPack.slug || ''),
        version_id: installVersionId ? String(installVersionId) : null,
        name: String(serverName).trim(),
        host_port: hostPort ? Number(hostPort) : null,
        min_ram: minRam,
        max_ram: maxRam,
      };
      const response = await fetch(`${API}/modpacks/install`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...safeAuthHeaders() },
        body: JSON.stringify(body)
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || `HTTP ${response.status}`);
      }
      const taskId = data?.task_id;
      if (!taskId) throw new Error('No task id');
      const es = new EventSource(`${API}/modpacks/install/events/${taskId}`);
      es.onmessage = event => {
        try {
          const parsed = JSON.parse(event.data);
          setInstallEvents(prev => {
            const next = [...prev, parsed];
            return next.length > 500 ? next.slice(-500) : next;
          });
          if (parsed.type === 'done' || parsed.type === 'error') {
            es.close();
            setInstallWorking(false);
          }
        } catch {
          // Ignore malformed event payloads
        }
      };
      es.onerror = () => {
        try {
          es.close();
        } catch {
          // noop
        }
        setInstallWorking(false);
      };
    } catch (error) {
      setInstallEvents(prev => [...prev, { type: 'error', message: String(error.message || error) }]);
      setInstallWorking(false);
    }
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-bold flex items-center gap-3">
          <FaLayerGroup className="text-brand-500" /> Templates & Modpacks
        </h1>
        <p className="text-white/70 mt-2">Import modpack server packs or search and install from providers</p>
      </div>

      <div className="bg-white/5 border border-white/10 rounded-lg p-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
          <div>
            <h3 className="text-lg font-semibold">Curated Marketplace</h3>
            <p className="text-sm text-white/60">Vetted "one-click" setups with community ratings.</p>
          </div>
          <div className="flex items-center gap-2 text-xs text-white/60">
            {curatedLoading ? <span>Syncing…</span> : null}
            <button
              type="button"
              onClick={() => refreshCurated()}
              className="px-3 py-1 rounded bg-white/10 hover:bg-white/20 text-white disabled:opacity-40"
              disabled={curatedLoading}
            >Refresh</button>
          </div>
        </div>
        {curatedError && <div className="text-sm text-red-400 mb-3">{curatedError}</div>}
        {curatedLoading && !curatedItems.length ? (
          <div className="text-sm text-white/60">Loading curated templates…</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {curatedItems.map(item => {
              const rating = typeof item.rating === 'number' ? item.rating.toFixed(1) : '—';
              const votes = typeof item.votes === 'number' ? numberFormatter.format(item.votes) : '0';
              const ram = item.recommended_ram;
              const serverTypeLabel = item.server_type ? String(item.server_type).toUpperCase() : 'TEMPLATE';
              const minecraftVersionLabel = item.minecraft_version || '—';
              const availabilityKey = String(item.availability || 'unknown').toLowerCase();
              const availabilityMeta = {
                ok: { label: 'Ready', tone: 'success' },
                'latest-used': { label: 'Ready • Latest used', tone: 'success' },
                'provider-unavailable': { label: 'Provider not configured', tone: 'warn' },
                'missing-pack': { label: 'Pack missing', tone: 'error' },
                'missing-version': { label: 'No versions', tone: 'error' },
                'invalid-metadata': { label: 'Invalid metadata', tone: 'error' },
                error: { label: 'Unavailable', tone: 'error' },
                unknown: { label: 'Status unknown', tone: 'warn' },
              }[availabilityKey] || { label: 'Status unknown', tone: 'warn' };
              const toneClasses = {
                success: 'bg-emerald-500/15 text-emerald-200 border border-emerald-400/30',
                warn: 'bg-amber-500/15 text-amber-100 border border-amber-400/30',
                error: 'bg-red-500/15 text-red-200 border border-red-400/30',
              };
              const availabilityBadgeClass = toneClasses[availabilityMeta.tone] || toneClasses.warn;
              const showInstallBlocked = new Set(['provider-unavailable', 'missing-pack', 'invalid-metadata', 'missing-version', 'error']).has(availabilityKey);
              const providerLabel = String(item.install?.provider || item.provider || 'modrinth');
              const providerConfigured = item.provider_configured !== false;
              const availabilityMessageClass = availabilityMeta.tone === 'success'
                ? 'text-emerald-100'
                : availabilityMeta.tone === 'error'
                  ? 'text-red-200'
                  : 'text-amber-100';
              return (
                <div key={item.id} className="p-4 rounded-lg border border-white/10 bg-black/20 flex flex-col gap-3">
                  <div>
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="font-semibold text-white">{item.name}</div>
                        <div className="text-xs text-white/60">
                          {serverTypeLabel} · MC {minecraftVersionLabel}
                        </div>
                      </div>
                      <div className="text-xs text-white/60 text-right">
                        <div>⭐ {rating}</div>
                        <div>{votes} votes</div>
                      </div>
                    </div>
                    <div className="text-sm text-white/70 mt-2 line-clamp-3">{item.short_description || item.description}</div>
                  </div>
                  {Array.isArray(item.tags) && item.tags.length ? (
                    <div className="flex flex-wrap gap-1 text-[11px] text-white/60">
                      {item.tags.slice(0, 6).map(tag => (
                        <span key={`${item.id}-${tag}`} className="px-2 py-0.5 rounded-full bg-white/10 border border-white/10">{tag}</span>
                      ))}
                    </div>
                  ) : null}
                  <div className="flex justify-between items-center text-[11px]">
                    <span className={`px-2 py-0.5 rounded-full ${availabilityBadgeClass}`}>{availabilityMeta.label}</span>
                    {!providerConfigured ? (
                      <span className="text-amber-100">Provider key not configured</span>
                    ) : null}
                  </div>
                  {item.availability_message ? (
                    <div className={`text-xs ${availabilityMessageClass}`}>{item.availability_message}</div>
                  ) : null}
                  <div className="text-xs text-white/50 space-y-1">
                    <div>Loader: {item.loader || item.server_type || '—'}</div>
                    {ram && ram.min && ram.max ? (
                      <div>Recommended RAM: {ram.min} – {ram.max}</div>
                    ) : null}
                    <div>Provider: {providerLabel}</div>
                    {item.verified_by ? <div>Verified by: {item.verified_by}</div> : null}
                  </div>
                  <div className="flex items-center gap-2 mt-auto">
                    <button
                      onClick={() => openCuratedInstall(item)}
                      className="px-3 py-1.5 rounded bg-brand-500 hover:bg-brand-600 text-sm disabled:opacity-40 disabled:cursor-not-allowed"
                      disabled={showInstallBlocked}
                    >Quick Install</button>
                    {item.homepage ? (
                      <a
                        href={item.homepage}
                        target="_blank"
                        rel="noreferrer"
                        className="px-3 py-1.5 rounded bg-white/10 hover:bg-white/20 text-sm text-white/80"
                      >Details</a>
                    ) : null}
                  </div>
                </div>
              );
            })}
            {!curatedItems.length && !curatedLoading ? (
              <div className="text-sm text-white/50">No curated templates are available yet.</div>
            ) : null}
          </div>
        )}
      </div>

      <div className="bg-white/5 border border-white/10 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">Import Local Server Pack (.zip)</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-white/70 mb-1">Server Name</label>
            <input
              value={serverName}
              onChange={e => setServerName(e.target.value)}
              className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white"
            />
          </div>
          <div>
            <label className="block text-sm text-white/70 mb-1">Host Port (optional)</label>
            <input
              value={hostPort}
              onChange={e => setHostPort(e.target.value)}
              className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white"
              placeholder="e.g. 25565"
            />
          </div>
          <div className="md:col-span-2">
            <label className="block text-sm text-white/70 mb-1">Select ZIP file</label>
            <input
              type="file"
              accept=".zip"
              onChange={event => setZipFile(event.target.files && event.target.files[0] ? event.target.files[0] : null)}
              className="w-full text-sm text-white"
            />
          </div>
          <div>
            <label className="block text-sm text-white/70 mb-1">Min RAM</label>
            <input
              value={minRam}
              onChange={e => setMinRam(e.target.value)}
              onBlur={() => {
                const value = normalizeRamInput(minRam);
                if (value) setMinRam(value);
              }}
              className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white"
              aria-describedby="zip-min-ram-help"
            />
            <div id="zip-min-ram-help" className="text-[11px] text-white/50 mt-1">Formats: 2048M, 2G, 2048.</div>
          </div>
          <div>
            <label className="block text-sm text-white/70 mb-1">Max RAM</label>
            <input
              value={maxRam}
              onChange={e => setMaxRam(e.target.value)}
              onBlur={() => {
                const value = normalizeRamInput(maxRam);
                if (value) setMaxRam(value);
              }}
              className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white"
              aria-describedby="zip-max-ram-help"
            />
            <div id="zip-max-ram-help" className="text-[11px] text-white/50 mt-1">Formats: 4096M, 4G, 4096.</div>
          </div>
          <div className="md:col-span-2 flex items-center gap-3">
            <button
              disabled={busy || !zipFile}
              onClick={async () => {
                setBusy(true);
                setMsg('');
                try {
                  const normMin = normalizeRamInput(minRam);
                  const normMax = normalizeRamInput(maxRam);
                  if (!normMin || !normMax) {
                    setMsg('Invalid RAM values. Examples: 2048M, 2G, 2048');
                    setBusy(false);
                    return;
                  }
                  const formData = new FormData();
                  formData.append('server_name', serverName);
                  if (hostPort) formData.append('host_port', hostPort);
                  formData.append('min_ram', normMin);
                  formData.append('max_ram', normMax);
                  if (javaOverride) formData.append('java_version_override', javaOverride);
                  if (serverType) formData.append('server_type', serverType);
                  if (serverVersion) formData.append('server_version', serverVersion);
                  if (zipFile) formData.append('file', zipFile);
                  const response = await fetch(`${API}/modpacks/import-upload`, { method: 'POST', body: formData });
                  const data = await response.json().catch(() => ({}));
                  if (!response.ok) {
                    throw new Error(data?.detail || `HTTP ${response.status}`);
                  }
                  setMsg('Server pack uploaded and container started. Go to Servers to see it.');
                } catch (error) {
                  setMsg(`Error: ${error.message || error}`);
                } finally {
                  setBusy(false);
                }
              }}
              className="bg-brand-500 hover:bg-brand-600 disabled:opacity-50 px-4 py-2 rounded flex items-center gap-2"
              aria-busy={busy}
              aria-live="polite"
            >
              {busy && (
                <span
                  className="animate-spin inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full"
                  aria-hidden="true"
                ></span>
              )}
              {busy ? 'Uploading…' : 'Import ZIP'}
            </button>
            {msg && <div className="text-sm text-white/70">{msg}</div>}
          </div>
        </div>
      </div>

      <div className="bg-white/5 border border-white/10 rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">Search for Modpack Name</h3>
          <div className="flex items-center gap-2 text-sm text-white/70">
            <button
              onClick={() => {
                if (!catalogLoading && catalogPage > 1) {
                  setCatalogPage(page => page - 1);
                  setTimeout(() => {
                    if (!catalogLoading) searchCatalog();
                  }, 0);
                }
              }}
              disabled={catalogLoading || catalogPage <= 1}
              className="px-2 py-1 bg-white/10 hover:bg-white/20 rounded disabled:opacity-50"
            >
              Prev
            </button>
            <span>Page {catalogPage}</span>
            <button
              onClick={() => {
                if (!catalogLoading) {
                  setCatalogPage(page => page + 1);
                  setTimeout(() => {
                    if (!catalogLoading) searchCatalog();
                  }, 0);
                }
              }}
              disabled={catalogLoading}
              className="px-2 py-1 bg-white/10 hover:bg-white/20 rounded disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4">
          <select
            className="rounded bg-white/10 border border-white/20 px-3 py-2 text-white"
            value={provider}
            onChange={e => setProvider(e.target.value)}
            style={{ backgroundColor: '#1f2937' }}
          >
            {providers.map(p => (
              <option
                key={p.id}
                value={p.id}
                disabled={p.requires_key && !p.configured}
                style={{ backgroundColor: '#1f2937' }}
              >
                {p.name}
                {p.requires_key && !p.configured ? ' (configure in Settings)' : ''}
              </option>
            ))}
          </select>
          <input
            className="rounded bg-white/5 border border-white/10 px-3 py-2 text-white placeholder-white/50"
            placeholder="Type modpack name (e.g. Beyond Cosmo)"
            value={catalogQuery}
            onChange={e => setCatalogQuery(e.target.value)}
          />
          <input
            className="rounded bg-white/5 border border-white/10 px-3 py-2 text-white placeholder-white/50"
            placeholder="MC Version (e.g. 1.20.4)"
            value={catalogMC}
            onChange={e => setCatalogMC(e.target.value)}
          />
          <select
            className="rounded bg-white/10 border border-white/20 px-3 py-2 text-white"
            value={catalogLoader}
            onChange={e => setCatalogLoader(e.target.value)}
            style={{ backgroundColor: '#1f2937' }}
          >
            <option value="" style={{ backgroundColor: '#1f2937' }}>
              Any Loader
            </option>
            <option value="fabric" style={{ backgroundColor: '#1f2937' }}>
              Fabric
            </option>
            <option value="forge" style={{ backgroundColor: '#1f2937' }}>
              Forge
            </option>
            <option value="neoforge" style={{ backgroundColor: '#1f2937' }}>
              NeoForge
            </option>
          </select>
          <div className="md:col-span-4 flex items-center gap-2">
            <button onClick={() => { setCatalogPage(1); searchCatalog(); }} className="bg-brand-500 hover:bg-brand-600 px-3 py-2 rounded">
              Search
            </button>
            {catalogLoading && <div className="text-sm text-white/60">Loading…</div>}
            {catalogError && <div className="text-sm text-red-400">{catalogError}</div>}
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {catalogResults.map((pack, idx) => (
            <div key={pack.id || pack.slug || idx} className="bg-white/5 border border-white/10 rounded-lg p-4 flex flex-col">
              <div className="flex items-center gap-3 mb-2">
                {pack.icon_url ? (
                  <img src={pack.icon_url} alt="" className="w-8 h-8 rounded" />
                ) : (
                  <div className="w-8 h-8 bg-white/10 rounded" />
                )}
                <div>
                  <div className="font-semibold">{pack.name}</div>
                  <div className="text-xs text-white/60">{(pack.categories || []).slice(0, 3).join(' · ')}</div>
                </div>
              </div>
              <div className="text-sm text-white/70 line-clamp-2">{pack.description}</div>
              <div className="mt-2 flex items-center gap-3 text-xs text-white/60">
                {typeof pack.downloads === 'number' && <span>⬇ {Intl.NumberFormat().format(pack.downloads)}</span>}
                {pack.updated && <span>Updated {new Date(pack.updated).toLocaleDateString()}</span>}
              </div>
              <div className="mt-3 flex items-center gap-2">
                <button onClick={() => openInstallFromCatalog(pack)} className="bg-brand-500 hover:bg-brand-600 px-3 py-1.5 rounded text-sm">
                  Install
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {installOpen && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-ink border border-white/10 rounded-lg p-6 w-full max-w-2xl">
            <div className="flex items-center justify-between mb-4">
              <div className="text-lg font-semibold">Install Modpack{installPack?.name ? `: ${installPack.name}` : ''}</div>
              <button
                onClick={() => {
                  setInstallOpen(false);
                  setInstallPack(null);
                }}
                className="text-white/60 hover:text-white"
              >
                Close
              </button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
              <div>
                <label className="block text-xs text-white/60 mb-1">Version</label>
                <select
                  className="w-full rounded bg-white/10 border border-white/20 px-3 py-2 text-white"
                  value={installVersionId}
                  onChange={e => setInstallVersionId(e.target.value)}
                  style={{ backgroundColor: '#1f2937' }}
                >
                  {installVersions.map(version => (
                    <option key={version.id} value={version.id} style={{ backgroundColor: '#1f2937' }}>
                      {version.name || version.version_number}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-white/60 mb-1">Server Name</label>
                <input
                  className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white"
                  value={serverName}
                  onChange={e => setServerName(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-white/60 mb-1">Host Port (optional)</label>
                <input
                  className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white"
                  value={hostPort}
                  onChange={e => setHostPort(e.target.value)}
                  placeholder="25565"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-white/60 mb-1">Min RAM</label>
                  <input
                    className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white"
                    value={minRam}
                    onChange={e => setMinRam(e.target.value)}
                  />
                </div>
                <div>
                  <label className="block text-xs text-white/60 mb-1">Max RAM</label>
                  <input
                    className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white"
                    value={maxRam}
                    onChange={e => setMaxRam(e.target.value)}
                  />
                </div>
              </div>
              <div className="md:col-span-2 flex items-center gap-2 mt-2">
                <button
                  disabled={installWorking}
                  onClick={submitInstall}
                  className="bg-brand-500 hover:bg-brand-600 disabled:opacity-50 px-4 py-2 rounded"
                >
                  {installWorking ? 'Installing…' : 'Start Install'}
                </button>
                <div className="text-sm text-white/70">{installPack?.provider || provider}</div>
              </div>
            </div>
            <div className="bg-white/5 border border-white/10 rounded p-3 h-40 overflow-auto text-sm">
              {installEvents.length === 0 ? (
                <div className="text-white/50">No events yet…</div>
              ) : (
                <ul className="space-y-1">
                  {installEvents.map((event, index) => {
                    let text = '';
                    if (typeof event?.message === 'string') {
                      text = event.message;
                    } else if (event?.message) {
                      try {
                        text = JSON.stringify(event.message);
                      } catch {
                        text = String(event.message);
                      }
                    } else if (event?.step) {
                      const pct = typeof event.progress === 'number' ? ` (${event.progress}%)` : '';
                      text = `${event.step}${pct}`;
                    } else {
                      try {
                        text = JSON.stringify(event);
                      } catch {
                        text = String(event);
                      }
                    }
                    return (
                      <li key={index} className="flex items-start gap-2">
                        <span
                          className="w-2 h-2 rounded-full mt-2"
                          style={{ background: event.type === 'error' ? '#f87171' : event.type === 'done' ? '#34d399' : '#a78bfa' }}
                        ></span>
                        <span>{text}</span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

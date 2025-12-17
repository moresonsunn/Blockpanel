import React, { useEffect, useMemo, useState } from 'react';
import { FaLayerGroup, FaPlusCircle } from 'react-icons/fa';
import { normalizeRamInput } from '../utils/ram';

const SERVER_TYPES_WITH_LOADER = ['fabric', 'forge', 'neoforge'];

const TMOD_WORLD_SIZE_OPTIONS = [
  { value: '1', label: 'Small' },
  { value: '2', label: 'Medium' },
  { value: '3', label: 'Large' },
];

const TMOD_WORLD_DIFFICULTY_OPTIONS = [
  { value: '0', label: 'Journey' },
  { value: '1', label: 'Classic' },
  { value: '2', label: 'Expert' },
  { value: '3', label: 'Master' },
];

const TMOD_WORLD_ENV_KEY_SET = new Set(['WORLD_NAME', 'WORLD_FILENAME', 'WORLD_SIZE', 'WORLD_DIFFICULTY', 'WORLD_SEED']);

export default function TemplatesPage({
  API,
  authHeaders,
  onCreateServer,
  types = [],
  versionsData,
  selectedType: createSelectedType,
  setSelectedType: setCreateSelectedType,
  name: createName,
  setName: setCreateName,
  version: createVersion,
  setVersion: setCreateVersion,
  hostPort: createHostPort,
  setHostPort: setCreateHostPort,
  minRam: createMinRam,
  setMinRam: setCreateMinRam,
  maxRam: createMaxRam,
  setMaxRam: setCreateMaxRam,
  loaderVersion: createLoaderVersion,
  setLoaderVersion: setCreateLoaderVersion,
  loaderVersionsData: createLoaderVersionsData,
  installerVersion: createInstallerVersion,
  setInstallerVersion: setCreateInstallerVersion,
}) {
  const safeAuthHeaders = useMemo(() => (typeof authHeaders === 'function' ? authHeaders : () => ({})), [authHeaders]);

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

  const [templatesTab, setTemplatesTab] = useState('minecraft');
  const [steamGames, setSteamGames] = useState([]);
  const [steamGamesLoading, setSteamGamesLoading] = useState(false);
  const [steamGamesError, setSteamGamesError] = useState('');
  const [steamSelectedGame, setSteamSelectedGame] = useState(null);
  const [steamForm, setSteamForm] = useState({ name: '', hostPort: '', env: {} });
  const [steamSubmitting, setSteamSubmitting] = useState(false);
  const [steamInstallResult, setSteamInstallResult] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function loadSteamGames() {
      setSteamGamesLoading(true);
      setSteamGamesError('');
      try {
        const response = await fetch(`${API}/steam/games`, { headers: safeAuthHeaders() });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          const message = data?.detail || `HTTP ${response.status}`;
          throw new Error(message);
        }
        if (!cancelled) {
          setSteamGames(Array.isArray(data?.games) ? data.games : []);
        }
      } catch (error) {
        if (!cancelled) {
          setSteamGames([]);
          setSteamGamesError(String(error?.message || error));
        }
      } finally {
        if (!cancelled) {
          setSteamGamesLoading(false);
        }
      }
    }
    loadSteamGames();
    return () => {
      cancelled = true;
    };
  }, [API, safeAuthHeaders]);

  const randomSuffix = () => Math.random().toString(36).slice(2, 6);

  function openSteamGameInstaller(game) {
    if (!game) {
      setSteamSelectedGame(null);
      setSteamInstallResult(null);
      setSteamForm({ name: '', hostPort: '', env: {} });
      return;
    }
    const baseName = game.default_name || game.slug || 'steam';
    const envDefaults = {};
    if (game.env && typeof game.env === 'object') {
      Object.entries(game.env).forEach(([key, value]) => {
        envDefaults[key] = value === undefined || value === null ? '' : String(value);
      });
    }
    setSteamSelectedGame(game);
    setSteamForm({
      name: `${baseName}-${randomSuffix()}`,
      hostPort: '',
      env: envDefaults,
    });
    setSteamInstallResult(null);
  }

  function updateSteamEnv(key, value) {
    setSteamForm((prev) => ({
      ...prev,
      env: { ...prev.env, [key]: value },
    }));
  }

  function updateSteamField(field, value) {
    setSteamForm((prev) => ({ ...prev, [field]: value }));
  }

  async function submitSteamInstall(e) {
    e.preventDefault();
    if (!steamSelectedGame) return;
    const trimmedName = (steamForm.name || '').trim();
    if (!trimmedName) {
      setSteamInstallResult({ ok: false, message: 'Server name is required.' });
      return;
    }

    setSteamSubmitting(true);
    setSteamInstallResult(null);

    try {
      const payload = {
        game: steamSelectedGame.slug,
        name: trimmedName,
      };

      const hostPortValue = (steamForm.hostPort || '').trim();
      if (hostPortValue) {
        const parsed = Number(hostPortValue);
        if (!Number.isInteger(parsed) || parsed <= 0 || parsed > 65535) {
          throw new Error('Host port must be a number between 1 and 65535.');
        }
        payload.host_port = parsed;
      }

      const envPayload = {};
      Object.entries(steamForm.env || {}).forEach(([key, value]) => {
        if (value === undefined || value === null) return;
        envPayload[key] = String(value);
      });
      if (Object.keys(envPayload).length > 0) {
        payload.env = envPayload;
      }

      const response = await fetch(`${API}/steam/install`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...safeAuthHeaders() },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = data?.detail || `HTTP ${response.status}`;
        throw new Error(detail);
      }

      setSteamInstallResult({ ok: true, data });
    } catch (error) {
      setSteamInstallResult({ ok: false, message: String(error?.message || error) });
    } finally {
      setSteamSubmitting(false);
    }
  }

  const [providers] = useState([
    { id: 'modrinth', name: 'Modrinth' },
    { id: 'curseforge', name: 'CurseForge' },
  ]);
  const [provider, setProvider] = useState('modrinth');
  const [catalogQuery, setCatalogQuery] = useState('');
  const [catalogLoader, setCatalogLoader] = useState('');
  const [catalogMC, setCatalogMC] = useState('');
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState('');
  const [catalogResults, setCatalogResults] = useState([]);
  const [catalogPage, setCatalogPage] = useState(1);
  const CATALOG_PAGE_SIZE = 24;

  const [installOpen, setInstallOpen] = useState(false);
  const [installPack, setInstallPack] = useState(null);
  const [installProvider, setInstallProvider] = useState('modrinth');
  const [installVersions, setInstallVersions] = useState([]);
  const [installVersionId, setInstallVersionId] = useState('');
  const [installEvents, setInstallEvents] = useState([]);
  const [installWorking, setInstallWorking] = useState(false);

  // Provider list is fixed (Modrinth & CurseForge), no curated marketplace.

  // Suggest a free host port for the create-server form when none is set yet.
  useEffect(() => {
    const controller = new AbortController();
    async function suggest() {
      if (createHostPort) return;
      try {
        const r = await fetch(`${API}/ports/suggest?start=25565&end=25999`, { signal: controller.signal });
        if (!r.ok) return;
        const d = await r.json();
        if (!controller.signal.aborted && d?.port) {
          setCreateHostPort(String(d.port));
        }
      } catch {}
    }
    suggest();
    return () => controller.abort();
  }, [API, createHostPort, setCreateHostPort]);

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
      const chosenProvider = providerOverride || provider || 'modrinth';
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
        provider: installProvider || provider || 'modrinth',
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

      {/* Tab switcher: Minecraft vs Steam (other games) */}
      <div className="bg-white/5 border border-white/10 rounded-lg p-1 flex w-full md:w-fit">
        <button
          onClick={() => setTemplatesTab('minecraft')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${templatesTab === 'minecraft' ? 'bg-brand-500 text-white' : 'text-white/70 hover:text-white hover:bg-white/10'}`}
        >Minecraft</button>
        <button
          onClick={() => setTemplatesTab('steam')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${templatesTab === 'steam' ? 'bg-brand-500 text-white' : 'text-white/70 hover:text-white hover:bg-white/10'}`}
        >Steam (Other Games)</button>
      </div>

      {templatesTab === 'minecraft' ? (
        <>
          <div className="bg-white/5 border border-white/10 rounded-lg p-6">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
              <div>
                <h3 className="text-lg font-semibold flex items-center gap-2">
                  <FaPlusCircle /> Create New Server
                </h3>
                <p className="text-sm text-white/60">Provision a fresh server without attaching a modpack.</p>
              </div>
            </div>
            <form onSubmit={(e) => { if (onCreateServer) { onCreateServer(e); } else { e.preventDefault(); } }} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium text-white/70 mb-2">Server Name</label>
                  <input
                    type="text"
                    value={createName}
                    onChange={(e) => setCreateName(e.target.value)}
                    className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white placeholder-white/50"
                    placeholder="Enter server name"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-white/70 mb-2">Server Type</label>
                  <select
                    value={createSelectedType}
                    onChange={(e) => setCreateSelectedType(e.target.value)}
                    className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded text-white"
                  >
                    {(types || []).map((t) => (
                      <option key={t} value={t} style={{ backgroundColor: '#1f2937' }}>{t}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-white/70 mb-2">Version</label>
                  <select
                    value={createVersion}
                    onChange={(e) => setCreateVersion(e.target.value)}
                    className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded text-white"
                  >
                    {(versionsData?.versions || []).map((v) => (
                      <option key={v} value={v} style={{ backgroundColor: '#1f2937' }}>{v}</option>
                    ))}
                  </select>
                </div>
              </div>

              {SERVER_TYPES_WITH_LOADER.includes(createSelectedType) && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-white/70 mb-2">Loader Version</label>
                    <select
                      value={createLoaderVersion}
                      onChange={(e) => setCreateLoaderVersion(e.target.value)}
                      className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded text-white"
                    >
                      {(createLoaderVersionsData?.loader_versions || []).map((lv) => (
                        <option key={lv} value={lv} style={{ backgroundColor: '#1f2937' }}>{lv}</option>
                      ))}
                    </select>
                  </div>
                  {createSelectedType === 'fabric' && (
                  <div>
                    <label className="block text-sm font-medium text-white/70 mb-2">Installer Version</label>
                    {Array.isArray(createLoaderVersionsData?.installer_versions) && createLoaderVersionsData.installer_versions.length > 0 ? (
                      <select
                        value={createInstallerVersion}
                        onChange={(e) => setCreateInstallerVersion(e.target.value)}
                        className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded text-white"
                      >
                        {createLoaderVersionsData.installer_versions.map((iv) => (
                          <option key={iv} value={iv} style={{ backgroundColor: '#1f2937' }}>{iv}</option>
                        ))}
                      </select>
                    ) : (
                      <input
                        type="text"
                        value={createInstallerVersion}
                        onChange={(e) => setCreateInstallerVersion(e.target.value)}
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white placeholder-white/50"
                        placeholder="e.g., 1.0.1"
                      />
                    )}
                    <div className="text-xs text-white/40 mt-1">
                      {createLoaderVersionsData?.latest_installer_version ? (
                        <button type="button" className="underline" onClick={() => setCreateInstallerVersion(createLoaderVersionsData.latest_installer_version)}>
                          Use latest: {createLoaderVersionsData.latest_installer_version}
                        </button>
                      ) : null}
                    </div>
                  </div>
                  )}
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium text-white/70 mb-2">Host Port</label>
                  <input
                    type="number"
                    value={createHostPort}
                    onChange={(e) => setCreateHostPort(e.target.value)}
                    className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white placeholder-white/50"
                    placeholder="25565"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-white/70 mb-2">Min RAM (MB)</label>
                  <input
                    type="number"
                    value={createMinRam}
                    onChange={(e) => setCreateMinRam(e.target.value)}
                    className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-white/70 mb-2">Max RAM (MB)</label>
                  <input
                    type="number"
                    value={createMaxRam}
                    onChange={(e) => setCreateMaxRam(e.target.value)}
                    className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white"
                  />
                </div>
              </div>

              <button
                type="submit"
                className="bg-brand-500 hover:bg-brand-600 px-6 py-3 rounded-lg text-white font-medium flex items-center gap-2"
              >
                <FaPlusCircle /> Create Server
              </button>
            </form>
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

          <div className="bg-white/5 border border-white/10 rounded-lg p-6 space-y-4">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold">Search Modpacks</h3>
                <p className="text-sm text-white/60">Find packs from Modrinth or CurseForge.</p>
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
        </>
      ) : (
        <div className="bg-white/5 border border-white/10 rounded-lg p-6 space-y-6">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div>
              <h3 className="text-lg font-semibold">Steam & Other Dedicated Servers</h3>
              <p className="text-sm text-white/60">Deploy curated Steam-compatible servers with one click. Containers appear under My Servers automatically.</p>
            </div>
            <span className="text-xs uppercase tracking-wide bg-brand-500/15 text-brand-200 px-3 py-1 rounded">Beta</span>
          </div>

          {steamGamesError ? (
            <div className="bg-red-500/10 border border-red-400/30 text-red-200 rounded-lg px-4 py-3 text-sm">
              {steamGamesError}
            </div>
          ) : null}

          {steamGamesLoading ? (
            <div className="text-sm text-white/60">Loading Steam catalog…</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {steamGames.map((game) => {
                const isSelected = steamSelectedGame?.slug === game.slug;
                return (
                  <div
                    key={game.slug || game.name}
                    className={`bg-white/5 border rounded-lg p-4 space-y-3 transition-all ${
                      isSelected ? 'border-brand-400/40 bg-brand-500/10 shadow-lg shadow-brand-500/20' : 'border-white/10'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-white font-semibold text-sm sm:text-base">{game.name || game.slug}</div>
                        <div className="text-xs text-white/50 mt-1 break-words">{game.summary || game.notes || 'Generic dedicated server template.'}</div>
                      </div>
                      <span className="text-xs bg-brand-500/15 text-brand-200 px-2 py-0.5 rounded">Linux</span>
                    </div>
                    <div className="text-xs text-white/50">
                      Ports: {(game.ports || []).map((p) => `${p.container}/${(p.protocol || 'tcp').toUpperCase()}`).join(', ') || 'n/a'}
                    </div>
                    <button
                      type="button"
                      onClick={() => openSteamGameInstaller(game)}
                      className={`w-full inline-flex items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                        isSelected ? 'bg-brand-500 text-white' : 'bg-white/10 text-white hover:bg-white/20'
                      }`}
                      disabled={steamSubmitting && !isSelected}
                    >
                      {isSelected ? 'Selected' : 'Deploy'}
                    </button>
                  </div>
                );
              })}
              {steamGames.length === 0 && !steamGamesError ? (
                <div className="col-span-full bg-white/5 border border-white/10 rounded-lg p-6 text-sm text-white/60 text-center">
                  No Steam templates available yet. Check back soon.
                </div>
              ) : null}
            </div>
          )}

          {steamSelectedGame ? (
            <div className="bg-black/20 border border-white/10 rounded-lg p-5 space-y-4">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div>
                  <h4 className="text-lg font-semibold text-white">Deploy {steamSelectedGame.name || steamSelectedGame.slug}</h4>
                  <p className="text-sm text-white/60 mt-1 max-w-2xl">Customize the container name, optional host port, and credentials before provisioning.</p>
                </div>
                <button
                  type="button"
                  onClick={() => openSteamGameInstaller(null)}
                  className="text-xs text-white/60 hover:text-white transition-colors"
                >
                  Clear selection
                </button>
              </div>

              {steamInstallResult ? (
                <div
                  className={`rounded-lg border px-4 py-3 text-sm ${
                    steamInstallResult.ok
                      ? 'bg-green-500/10 border-green-400/30 text-green-100'
                      : 'bg-red-500/10 border-red-400/30 text-red-100'
                  }`}
                >
                  <div className="font-semibold">
                    {steamInstallResult.ok ? 'Install request queued' : 'Install failed'}
                  </div>
                  <div className="mt-1 text-xs text-white/80">
                    {steamInstallResult.ok
                      ? 'Docker is provisioning the container now. It will appear under My Servers shortly.'
                      : steamInstallResult.message}
                  </div>
                  {steamInstallResult.ok && steamInstallResult.data?.ports ? (
                    <div className="mt-3 text-xs text-white/80 space-y-1">
                      <div className="font-semibold text-white">Assigned ports</div>
                      {Object.entries(steamInstallResult.data.ports).map(([key, host]) => (
                        <div key={key} className="flex justify-between gap-4">
                          <span className="text-white/60">{key}</span>
                          <span className="text-white">{host}</span>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {steamInstallResult.ok && steamInstallResult.data?.env ? (
                    <div className="mt-3 text-xs text-white/80 space-y-1">
                      <div className="font-semibold text-white">Saved credentials</div>
                      {Object.entries(steamInstallResult.data.env).map(([key, value]) => (
                        <div key={key} className="flex justify-between gap-4">
                          <span className="text-white/60">{key}</span>
                          <span className="text-white">{value}</span>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {steamInstallResult.ok && steamInstallResult.data?.data_path ? (
                    <div className="mt-3 text-xs text-white/60">Data directory: {steamInstallResult.data.data_path}</div>
                  ) : null}
                </div>
              ) : null}

              <form onSubmit={submitSteamInstall} className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs text-white/60 mb-1">Server name</label>
                    <input
                      className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white"
                      value={steamForm.name}
                      onChange={(e) => updateSteamField('name', e.target.value)}
                      placeholder={`${steamSelectedGame.default_name || steamSelectedGame.slug}-server`}
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-white/60 mb-1">Host port (optional)</label>
                    <input
                      className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white"
                      value={steamForm.hostPort}
                      onChange={(e) => updateSteamField('hostPort', e.target.value.replace(/[^0-9]/g, ''))}
                      placeholder="Auto-assign"
                      inputMode="numeric"
                    />
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="text-xs uppercase tracking-wide text-white/50">Environment overrides</div>
                  {steamSelectedGame?.slug === 'tmodloader' ? (
                    <div className="bg-white/5 border border-white/10 rounded-lg p-3 space-y-3">
                      <div className="text-xs text-white/60 uppercase tracking-wide">Terraria world setup</div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div className="space-y-1">
                          <label className="block text-xs text-white/60">World name</label>
                          <input
                            className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white"
                            value={steamForm.env?.WORLD_NAME ?? ''}
                            onChange={(e) => updateSteamEnv('WORLD_NAME', e.target.value)}
                            placeholder="Dedicated"
                          />
                        </div>
                        <div className="space-y-1">
                          <label className="block text-xs text-white/60">World filename</label>
                          <input
                            className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white"
                            value={steamForm.env?.WORLD_FILENAME ?? ''}
                            onChange={(e) => updateSteamEnv('WORLD_FILENAME', e.target.value)}
                            placeholder="Dedicated.wld"
                          />
                          <div className="text-[11px] text-white/40">Ends with .wld and must exist or be generated.</div>
                        </div>
                        <div className="space-y-1">
                          <label className="block text-xs text-white/60">World size</label>
                          <select
                            className="w-full rounded bg-white/10 border border-white/20 px-3 py-2 text-white"
                            value={steamForm.env?.WORLD_SIZE === undefined || steamForm.env.WORLD_SIZE === null ? '3' : String(steamForm.env.WORLD_SIZE)}
                            onChange={(e) => updateSteamEnv('WORLD_SIZE', e.target.value)}
                            style={{ backgroundColor: '#1f2937' }}
                          >
                            {TMOD_WORLD_SIZE_OPTIONS.map((option) => (
                              <option key={option.value} value={option.value} style={{ backgroundColor: '#1f2937' }}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div className="space-y-1">
                          <label className="block text-xs text-white/60">World difficulty</label>
                          <select
                            className="w-full rounded bg-white/10 border border-white/20 px-3 py-2 text-white"
                            value={steamForm.env?.WORLD_DIFFICULTY === undefined || steamForm.env.WORLD_DIFFICULTY === null ? '1' : String(steamForm.env.WORLD_DIFFICULTY)}
                            onChange={(e) => updateSteamEnv('WORLD_DIFFICULTY', e.target.value)}
                            style={{ backgroundColor: '#1f2937' }}
                          >
                            {TMOD_WORLD_DIFFICULTY_OPTIONS.map((option) => (
                              <option key={option.value} value={option.value} style={{ backgroundColor: '#1f2937' }}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div className="space-y-1">
                          <label className="block text-xs text-white/60">World seed (optional)</label>
                          <input
                            className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white"
                            value={steamForm.env?.WORLD_SEED ?? ''}
                            onChange={(e) => updateSteamEnv('WORLD_SEED', e.target.value)}
                            placeholder="Random"
                          />
                        </div>
                      </div>
                      <div className="text-[11px] text-white/40">Adjust size and difficulty before first launch to generate the desired world.</div>
                    </div>
                  ) : null}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {Object.keys(steamForm.env || {}).length === 0 ? (
                      <div className="text-xs text-white/50">No environment variables exposed for this template.</div>
                    ) : null}
                    {Object.entries(steamForm.env || {}).map(([key, value]) => {
                      if (steamSelectedGame?.slug === 'tmodloader' && TMOD_WORLD_ENV_KEY_SET.has(key)) {
                        return null;
                      }
                      const isSecret = key.toLowerCase().includes('password') || key.toLowerCase().includes('token');
                      return (
                        <div key={key} className="space-y-1">
                          <label className="block text-xs text-white/60">{key}</label>
                          <input
                            type={isSecret ? 'password' : 'text'}
                            className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white"
                            value={value ?? ''}
                            onChange={(e) => updateSteamEnv(key, e.target.value)}
                          />
                        </div>
                      );
                    })}
                  </div>
                  <div className="text-xs text-white/40">Leave fields untouched to use the recommended defaults. Password fields are generated automatically if left as placeholders.</div>
                </div>

                <div className="flex items-center gap-3">
                  <button
                    type="submit"
                    disabled={steamSubmitting}
                    className="inline-flex items-center gap-2 rounded-md bg-brand-500 hover:bg-brand-600 disabled:opacity-60 px-4 py-2 text-sm font-medium text-white transition-colors"
                  >
                    {steamSubmitting ? 'Provisioning…' : 'Provision Server'}
                  </button>
                  <div className="text-xs text-white/50">Provisioning may take up to a minute depending on download size.</div>
                </div>
              </form>
            </div>
          ) : (
            <div className="bg-black/20 border border-white/10 rounded-lg p-5 text-sm text-white/60">
              Select a game above to review default settings and deploy. The controller assigns open host ports automatically when none are provided.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

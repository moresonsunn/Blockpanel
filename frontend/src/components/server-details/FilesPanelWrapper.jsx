import React, { useEffect, useMemo, useRef, useState } from 'react';
import { FaFolder, FaUpload, FaSave, FaEdit } from 'react-icons/fa';

const API = 'http://localhost:8000';

export default function FilesPanelWrapper({ serverName, initialItems = null, isBlockedFile, onEditStart, onBlockedFileError }) {
  const [path, setPath] = useState('.');
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const [blockedFileErrorLocal, setBlockedFileErrorLocal] = useState('');
  const [renameTarget, setRenameTarget] = useState(null);
  const [renameValue, setRenameValue] = useState('');

  // Simple in-memory cache for directory listings per server
  // cacheRef.current[key] = { items, ts }
  const cacheRef = useRef({});
  const abortRef = useRef(null);

  function withTimeout(promise, ms, controller) {
    return new Promise((resolve, reject) => {
      const id = setTimeout(() => {
        try { controller && controller.abort && controller.abort(); } catch {}
        reject(new DOMException('Timeout', 'AbortError'));
      }, ms);
      promise.then((v) => { clearTimeout(id); resolve(v); }).catch((e) => { clearTimeout(id); reject(e); });
    });
  }

  useEffect(() => {
    // clear cache when server changes
    cacheRef.current = {};
    const key = `${serverName}::.`;
    if (Array.isArray(initialItems) && initialItems.length) {
      // hydrate immediately for instant render
      cacheRef.current[key] = { items: initialItems, ts: Date.now(), etag: undefined };
      setItems(initialItems);
      setPath('.');
      // revalidate in background
      loadDir('.', { force: true });
    } else {
      loadDir('.', { force: true });
    }
  }, [serverName, initialItems]);

  async function loadDir(p = path, { force = false } = {}) {
    const key = `${serverName}::${p}`;
    setErr('');
    const cached = cacheRef.current[key];

    // Use cached data if fresh and not forced
    const now = Date.now();
    const TTL = 15000; // 15s cache
    if (!force && cached && now - cached.ts < TTL) {
      setItems(cached.items || []);
      setPath(p);
      return;
    }

    // Abort any in-flight fetch for previous path
    try { abortRef.current?.abort(); } catch {}
    const abortController = new AbortController();
    abortRef.current = abortController;

    const attempt = async () => {
      const headers = {};
      if (cached && force && cached.etag) headers['If-None-Match'] = cached.etag;
      const r = await withTimeout(
        fetch(`${API}/servers/${encodeURIComponent(serverName)}/files?path=${encodeURIComponent(p)}`, { signal: abortController.signal, headers }),
        8000,
        abortController
      );
      if (r.status === 304 && cached) {
        cacheRef.current[key] = { ...cached, ts: Date.now() };
        setItems(cached.items || []);
        setPath(p);
        return;
      }
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      const list = d.items || [];
      const etag = r.headers.get('etag') || (cached ? cached.etag : undefined);
      cacheRef.current[key] = { items: list, ts: Date.now(), etag };
      setItems(list);
      setPath(p);
    };

    setLoading(true);
    try {
      await attempt();
    } catch (e) {
      if (e?.name === 'AbortError') return;
      // simple retry once
      try {
        await new Promise(res => setTimeout(res, 400));
        await attempt();
      } catch (e2) {
        if (e2?.name === 'AbortError') return;
        setErr(String(e2));
      }
    } finally {
      setLoading(false);
    }
  }

  async function openFile(name) {
    setBlockedFileErrorLocal('');
    onBlockedFileError?.('');
    if (isBlockedFile && isBlockedFile(name)) {
      const msg = 'Cannot open this file type in the editor.';
      setBlockedFileErrorLocal(msg);
      onBlockedFileError?.(msg);
      return;
    }
    const filePath = path === '.' ? name : `${path}/${name}`;
    const r = await fetch(
      `${API}/servers/${encodeURIComponent(serverName)}/file?path=${encodeURIComponent(filePath)}`
    );
    const d = await r.json();
    if (d && d.error) {
      setBlockedFileErrorLocal(d.error);
      onBlockedFileError?.(d.error);
      return;
    }
    onEditStart?.(filePath, d.content || '');
  }

  async function openDir(name) {
    await loadDir(path === '.' ? name : `${path}/${name}`);
  }
  function goUp() {
    if (path === '.' || !path) return;
    const parts = path.split('/');
    parts.pop();
    const p = parts.length ? parts.join('/') : '.';
    loadDir(p);
  }
  async function del(name) {
    const p = path === '.' ? name : `${path}/${name}`;
    await fetch(
      `${API}/servers/${encodeURIComponent(serverName)}/file?path=${encodeURIComponent(p)}`,
      { method: 'DELETE' }
    );
    loadDir(path, { force: true });
  }

  async function renameCommit(originalName) {
    const p = path === '.' ? originalName : `${path}/${originalName}`;
    const newName = renameValue && renameValue.trim();
    if (!newName || newName === originalName) { setRenameTarget(null); return; }
    const dest = path === '.' ? newName : `${path}/${newName}`;
    await fetch(`${API}/servers/${encodeURIComponent(serverName)}/rename`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ src: p, dest })
    });
    setRenameTarget(null);
    setRenameValue('');
    loadDir(path, { force: true });
  }
  function startRename(name) {
    setRenameTarget(name);
    setRenameValue(name);
  }
  function cancelRename() {
    setRenameTarget(null);
    setRenameValue('');
  }

  async function zipItem(name) {
    const p = path === '.' ? name : `${path}/${name}`;
    await fetch(`${API}/servers/${encodeURIComponent(serverName)}/zip`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: p })
    });
    loadDir(path, { force: true });
  }

  async function unzipItem(name) {
    const p = path === '.' ? name : `${path}/${name}`;
    const defaultDest = name.toLowerCase().endsWith('.zip') ? name.slice(0, -4) : `${name}-unzipped`;
    const destInput = window.prompt('Unzip destination folder (relative to current path):', defaultDest);
    const destRel = destInput && destInput.trim() ? destInput.trim() : defaultDest;
    const dest = path === '.' ? destRel : `${path}/${destRel}`;
    await fetch(`${API}/servers/${encodeURIComponent(serverName)}/unzip`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: p, dest })
    });
    loadDir(path, { force: true });
  }

  async function createFolder() {
    const folder = window.prompt('New folder name');
    if (!folder) return;
    const p = path === '.' ? folder : `${path}/${folder}`;
    await fetch(`${API}/servers/${encodeURIComponent(serverName)}/mkdir`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: p })
    });
    loadDir(path, { force: true });
  }

  async function upload(ev) {
    const files = Array.from(ev.target.files || []);
    if (!files.length) return;
    const fd = new window.FormData();
    fd.append('path', path);
    for (const file of files) {
      fd.append('files', file);
    }
    await fetch(
      `${API}/servers/${encodeURIComponent(serverName)}/upload-multiple`,
      { method: 'POST', body: fd }
    );
    loadDir(path, { force: true });
  }

  const sortedItems = useMemo(() => {
    return [...items].sort((a, b) => {
      if (a.is_dir && !b.is_dir) return -1;
      if (!a.is_dir && b.is_dir) return 1;
      return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' });
    });
  }, [items]);

  // Prefetch throttle map
  const lastPrefetchRef = useRef({});
  const inflightPrefetchRef = useRef({});

  async function prefetchDir(dirPath) {
    const key = `${serverName}::${dirPath}`;
    const now = Date.now();
    const last = lastPrefetchRef.current[key] || 0;
    if (now - last < 400) return; // throttle
    lastPrefetchRef.current[key] = now;

    if (cacheRef.current[key]) return; // already cached
    if (inflightPrefetchRef.current[key]) return; // already fetching

    inflightPrefetchRef.current[key] = true;
    try {
      const r = await fetch(
        `${API}/servers/${encodeURIComponent(serverName)}/files?path=${encodeURIComponent(dirPath)}`
      );
      if (!r.ok) return;
      const d = await r.json();
      cacheRef.current[key] = { items: d.items || [], ts: now };
    } catch {}
    finally {
      delete inflightPrefetchRef.current[key];
    }
  }

  const listRef = useRef(null);
  const [scrollTop, setScrollTop] = useState(0);
  const CONTAINER_MAX_HEIGHT = 420;
  const ROW_H = 36;

  return (
    <div className="p-2 bg-black/20 rounded-lg" style={{ maxWidth: 520, minWidth: 320 }}>
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs text-white/70">
          Path: <span className="text-white">{path}</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={goUp}
            className="text-xs rounded bg-white/10 hover:bg-white/20 px-2 py-1"
          >
            Up
          </button>
          <button
            onClick={createFolder}
            className="text-xs rounded bg-white/10 hover:bg-white/20 px-2 py-1"
          >
            New Folder
          </button>
          <label className="text-xs rounded bg-brand-500 hover:bg-brand-400 px-2 py-1 cursor-pointer inline-flex items-center gap-2">
            <FaUpload /> Upload
            <input type="file" className="hidden" multiple onChange={upload} />
          </label>
          <button onClick={() => loadDir(path, { force: true })} className="text-xs rounded bg-white/10 hover:bg-white/20 px-2 py-1">Refresh</button>
        </div>
      </div>
      {loading && <div className="text-white/70 text-xs">Loading…</div>}
      {err && (
        <div className="text-red-400 text-xs flex items-center gap-2">
          <span>{err}</span>
          <button onClick={() => loadDir(path, { force: true })} className="text-white/80 underline">Retry</button>
        </div>
      )}
      {blockedFileErrorLocal && <div className="text-red-400 text-xs">{blockedFileErrorLocal}</div>}
      {!loading && (
        (() => {
          const containerHeight = listRef.current?.clientHeight || CONTAINER_MAX_HEIGHT;
          const visibleCount = Math.ceil(containerHeight / ROW_H) + 10; // buffer
          const startIndex = Math.max(0, Math.floor(scrollTop / ROW_H) - 5);
          const endIndex = Math.min(sortedItems.length, startIndex + visibleCount);
          const topPad = startIndex * ROW_H;
          const bottomPad = Math.max(0, (sortedItems.length - endIndex) * ROW_H);
          const visibleItems = sortedItems.slice(startIndex, endIndex);

          const renderRow = (it) => (
            <div
              key={it.name}
              className="flex items-center justify-between bg-white/5 border border-white/10 rounded px-2 py-1"
              style={{ minHeight: 32 }}
              onMouseEnter={() => { if (it.is_dir) prefetchDir(path === '.' ? it.name : `${path}/${it.name}`); }}
            >
              <div className="flex items-center gap-2">
                <span className="text-yellow-400 text-base">
                  {it.is_dir ? <FaFolder /> : '📄'}
                </span>
                {renameTarget === it.name ? (
                  <div className="flex items-center gap-1">
                    <input
                      className="text-xs bg-white/10 border border-white/20 rounded px-1 py-0.5 text-white"
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter') renameCommit(it.name); if (e.key === 'Escape') cancelRename(); }}
                      autoFocus
                      style={{ width: 160 }}
                    />
                    <button onClick={() => renameCommit(it.name)} className="text-xs rounded bg-brand-500 hover:bg-brand-400 px-2 py-0.5">Save</button>
                    <button onClick={cancelRename} className="text-xs rounded bg-white/10 hover:bg-white/20 px-2 py-0.5">Cancel</button>
                  </div>
                ) : (
                  <span className="text-xs">{it.name}</span>
                )}
              </div>
              <div className="flex items-center gap-1 text-xs">
                {it.is_dir ? (
                  <>
                    <button
                      onClick={() => openDir(it.name)}
                      className="rounded bg-white/10 hover:bg-white/20 px-2 py-1"
                    >
                      Open
                    </button>
                    <button
                      onClick={() => zipItem(it.name)}
                      className="rounded bg-white/10 hover:bg-white/20 px-2 py-1"
                    >
                      Zip
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={() => openFile(it.name)}
                      className="rounded bg-white/10 hover:bg-white/20 px-2 py-1 inline-flex items-center gap-1"
                      disabled={isBlockedFile && isBlockedFile(it.name)}
                      style={isBlockedFile && isBlockedFile(it.name) ? { opacity: 0.5, pointerEvents: 'none' } : {}}
                      title={isBlockedFile && isBlockedFile(it.name) ? "Cannot open this file type in the editor" : "Edit"}
                    >
                      <FaSave /> Edit
                    </button>
                    {it.name.toLowerCase().endsWith('.zip') ? (
                      <button
                        onClick={() => unzipItem(it.name)}
                        className="rounded bg-white/10 hover:bg-white/20 px-2 py-1"
                      >
                        Unzip
                      </button>
                    ) : (
                      <button
                        onClick={() => zipItem(it.name)}
                        className="rounded bg-white/10 hover:bg-white/20 px-2 py-1"
                      >
                        Zip
                      </button>
                    )}
                  </>
                )}
                <button
                  onClick={() => startRename(it.name)}
                  className="rounded bg-white/10 hover:bg-white/20 px-2 py-1 inline-flex items-center gap-1"
                  title="Rename"
                >
                  <FaEdit /> Rename
                </button>
                <button
                  onClick={() => del(it.name)}
                  className="rounded bg-red-600 hover:bg-red-500 px-2 py-1"
                >
                  Delete
                </button>
              </div>
            </div>
          );

          return (
            <div
              ref={listRef}
              style={{ maxHeight: CONTAINER_MAX_HEIGHT, overflowY: 'auto' }}
              onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
            >
              <div style={{ height: topPad }} />
              <div className="space-y-1">
                {visibleItems.map(renderRow)}
              </div>
              <div style={{ height: bottomPad }} />
            </div>
          );
        })()
      )}
    </div>
  );
}


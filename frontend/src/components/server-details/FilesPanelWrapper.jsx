import React, { useEffect, useMemo, useRef, useState } from 'react';
import { FaFolder, FaUpload, FaSave, FaEdit, FaTimes, FaCheck, FaBan, FaArrowUp, FaSyncAlt, FaFolderPlus } from 'react-icons/fa';
import { API, getStoredToken } from '../../lib/api';

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
  const uploadAbortersRef = useRef({}); // key: fileId -> AbortController/XHR

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
    // Optimistic remove from current list
    setItems(prev => prev.filter(it => it.name !== name));
    // Bust cache for this directory to avoid stale 304
    try { delete cacheRef.current[`${serverName}::${path}`]; } catch {}
    try {
      const r = await fetch(
        `${API}/servers/${encodeURIComponent(serverName)}/file?path=${encodeURIComponent(p)}`,
        { method: 'DELETE' }
      );
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
    } catch (e) {
      console.error('Delete failed:', e);
    } finally {
      loadDir(path, { force: true });
    }
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
    try { delete cacheRef.current[`${serverName}::${path}`]; } catch {}
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
    try { delete cacheRef.current[`${serverName}::${path}`]; } catch {}
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
    try { delete cacheRef.current[`${serverName}::${path}`]; } catch {}
    await fetch(`${API}/servers/${encodeURIComponent(serverName)}/unzip`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: p, dest })
    });
    loadDir(path, { force: true });
  }

  async function downloadItem(name, isDir) {
    const p = path === '.' ? name : `${path}/${name}`;
    const url = `${API}/servers/${encodeURIComponent(serverName)}/download?path=${encodeURIComponent(p)}`;
    try {
      const token = getStoredToken();
      const r = await fetch(url, { headers: token ? { 'Authorization': `Bearer ${token}` } : {} });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const blob = await r.blob();
      const a = document.createElement('a');
      const blobUrl = URL.createObjectURL(blob);
      a.href = blobUrl;
      a.download = isDir ? `${name}.zip` : name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(blobUrl), 2000);
    } catch (e) {
      alert(`Download failed: ${e}`);
    }
  }

  async function createFolder() {
    const folder = window.prompt('New folder name');
    if (!folder) return;
    const p = path === '.' ? folder : `${path}/${folder}`;
    try { delete cacheRef.current[`${serverName}::${path}`]; } catch {}
    await fetch(`${API}/servers/${encodeURIComponent(serverName)}/mkdir`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: p })
    });
    loadDir(path, { force: true });
  }
  // ---------- Upload with progress (XHR per file) ----------
  const [uploads, setUploads] = useState([]);
  const [aggregate, setAggregate] = useState({ totalBytes: 0, sentBytes: 0, inProgress: false, error: '' });
  const aggRef = useRef({ totalBytes: 0, sentBytes: 0 });
  const perFileLoadedRef = useRef({});
  const [isDropping, setIsDropping] = useState(false);

  function addUploads(newFiles, opts = {}) {
    // opts.destPath overrides destination directory for all files
    const now = Date.now();
    const toAdd = Array.from(newFiles).map((f, idx) => ({
      id: `${now}_${idx}_${f.name}`,
      file: f,
      name: f.name,
      size: f.size,
      destPath: opts.destPath || path,
      progress: 0,
      status: 'pending', // pending | uploading | done | error | cancelled
      error: ''
    }));
    setUploads(prev => [...prev, ...toAdd]);
    const total = toAdd.reduce((s, it) => s + (it.size || 0), 0);
  aggRef.current = { totalBytes: total, sentBytes: 0 };
  perFileLoadedRef.current = {};
  setAggregate({ totalBytes: total, sentBytes: 0, inProgress: true, error: '' });
    // Kick off sequential uploads but only track aggregate progress
    setTimeout(() => {
      startBatchUpload(toAdd);
    }, 0);
  }

  function addFolderUploads(fileList) {
    // For inputs with webkitdirectory, each File has webkitRelativePath
    const files = Array.from(fileList || []);
    if (files.length === 0) return;
    const now = Date.now();
    const toAdd = files.map((f, idx) => {
      const rel = (f.webkitRelativePath || f.relativePath || f.name);
      const relDir = rel.includes('/') ? rel.substring(0, rel.lastIndexOf('/')) : '';
      const dest = relDir ? (path === '.' ? relDir : `${path}/${relDir}`) : path;
      return {
        id: `${now}_${idx}_${f.name}`,
        file: f,
        name: f.name,
        size: f.size,
        destPath: dest,
        progress: 0,
        status: 'pending',
        error: ''
      };
    });
    setUploads(prev => [...prev, ...toAdd]);
    const total = toAdd.reduce((s, it) => s + (it.size || 0), 0);
  aggRef.current = { totalBytes: total, sentBytes: 0 };
  perFileLoadedRef.current = {};
  setAggregate({ totalBytes: total, sentBytes: 0, inProgress: true, error: '' });
    setTimeout(() => {
      startBatchUpload(toAdd);
    }, 0);
  }

  function formatBytes(n) {
    if (!Number.isFinite(n)) return '0 B';
    const units = ['B','KB','MB','GB'];
    let u = 0;
    let x = n;
    while (x >= 1024 && u < units.length - 1) { x /= 1024; u++; }
    return `${x.toFixed(x >= 100 ? 0 : x >= 10 ? 1 : 2)} ${units[u]}`;
  }

  async function startBatchUpload(items) {
    // Upload files sequentially; update aggregate progress using loaded bytes from each xhr
    for (const item of items) {
      const ok = await uploadOne(item);
      if (!ok) {
        setAggregate(a => ({ ...a, inProgress: false, error: 'One or more files failed to upload' }));
        // continue with next files but keep error shown
      }
    }
    setAggregate(a => ({ ...a, inProgress: false }));
    loadDir(path, { force: true });
    // Auto-dismiss upload tray when finished
    setTimeout(() => {
      const allDone = (arr) => arr.every(u => ['done','error','cancelled'].includes(u.status));
      if (!aggregate.inProgress) {
        setUploads(prev => allDone(prev) ? [] : prev);
        if (allDone(uploads)) setAggregate({ totalBytes: 0, sentBytes: 0, inProgress: false, error: '' });
      }
    }, 800);
  }

  function startSingleUpload(item) {
    const token = getStoredToken();
    const xhr = new XMLHttpRequest();
    uploadAbortersRef.current[item.id] = xhr;
    const dest = item.destPath || path;
    const url = `${API}/servers/${encodeURIComponent(serverName)}/upload?path=${encodeURIComponent(dest)}`;
    xhr.open('POST', url, true);
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    // Progress
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const prevLoaded = perFileLoadedRef.current[item.id] || 0;
        const delta = Math.max(0, e.loaded - prevLoaded);
        perFileLoadedRef.current[item.id] = e.loaded;
        aggRef.current.sentBytes = Math.min(aggRef.current.totalBytes, aggRef.current.sentBytes + delta);
        const pct = Math.round((e.loaded / e.total) * 100);
        setUploads(prev => prev.map(u => u.id === item.id ? { ...u, progress: pct, status: 'uploading' } : u));
        setAggregate({ ...aggregate, totalBytes: aggRef.current.totalBytes, sentBytes: aggRef.current.sentBytes, inProgress: true, error: '' });
      }
    };
    xhr.onerror = () => {
      setUploads(prev => prev.map(u => u.id === item.id ? { ...u, status: 'error', error: 'Network error' } : u));
    };
    xhr.onabort = () => {
      setUploads(prev => prev.map(u => u.id === item.id ? { ...u, status: 'cancelled', error: 'Cancelled' } : u));
    };
    xhr.onload = () => {
      const ok = xhr.status >= 200 && xhr.status < 300;
      setUploads(prev => prev.map(u => u.id === item.id ? { ...u, status: ok ? 'done' : 'error', error: ok ? '' : (`HTTP ${xhr.status}`) } : u));
      if (ok) {
        // Refresh listing to reflect newly uploaded file(s)
        loadDir(path, { force: true });
      }
    };
    const fd = new FormData();
    fd.append('file', item.file);
    xhr.send(fd);
  }

  const uProgressCache = {};

  function uploadOne(item) {
    return new Promise((resolve) => {
      const token = getStoredToken();
      const xhr = new XMLHttpRequest();
      uploadAbortersRef.current[item.id] = xhr;
      const dest = item.destPath || path;
      const url = `${API}/servers/${encodeURIComponent(serverName)}/upload?path=${encodeURIComponent(dest)}`;
      xhr.open('POST', url, true);
      if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
      perFileLoadedRef.current[item.id] = 0;
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const prevLoaded = perFileLoadedRef.current[item.id] || 0;
          const delta = Math.max(0, e.loaded - prevLoaded);
          perFileLoadedRef.current[item.id] = e.loaded;
          aggRef.current.sentBytes = Math.min(aggRef.current.totalBytes, aggRef.current.sentBytes + delta);
          setAggregate({ ...aggregate, totalBytes: aggRef.current.totalBytes, sentBytes: aggRef.current.sentBytes, inProgress: true, error: '' });
        }
      };
      xhr.onerror = () => { resolve(false); };
      xhr.onabort = () => { resolve(false); };
      xhr.onload = () => { resolve(xhr.status >= 200 && xhr.status < 300); };
      const fd = new FormData();
      fd.append('file', item.file);
      xhr.send(fd);
    });
  }

  function cancelUpload(id) {
    const ctrl = uploadAbortersRef.current[id];
    if (ctrl && ctrl.abort) {
      try { ctrl.abort(); } catch(_) {}
    } else if (ctrl && ctrl.readyState && ctrl.readyState !== 4) {
      try { ctrl.abort(); } catch(_) {}
    }
    setUploads(prev => prev.map(u => u.id === id ? { ...u, status: 'cancelled', error: 'Cancelled' } : u));
  }

  async function upload(ev) {
    const files = Array.from(ev.target.files || []);
    if (!files.length) return;
    addUploads(files);
    // reset the input value so selecting same file again triggers change
    ev.target.value = '';
  }

  function onDrop(ev) {
    ev.preventDefault(); ev.stopPropagation(); setIsDropping(false);
    const files = Array.from(ev.dataTransfer.files || []);
    if (!files.length) return;
    addUploads(files);
  }
  function onDragOver(ev) { ev.preventDefault(); ev.stopPropagation(); setIsDropping(true); }
  function onDragLeave(ev) { ev.preventDefault(); ev.stopPropagation(); setIsDropping(false); }

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
    <div className="p-2 bg-black/20 rounded-lg" style={{ maxWidth: 520, minWidth: 320 }}
         onDragOver={onDragOver}
         onDragLeave={onDragLeave}
         onDrop={onDrop}>
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs text-white/70 truncate">
          Path: <span className="text-white font-mono">{path}</span>
        </div>
        <div className="flex items-center gap-2">
          {(() => {
            const btn = "inline-flex items-center gap-1 rounded-md border border-white/10 bg-white/10 hover:bg-white/20 px-2 h-7 text-xs leading-none";
            const btnPrimary = "inline-flex items-center gap-1 rounded-md bg-brand-500 hover:bg-brand-400 text-white px-2 h-7 text-xs leading-none";
            return (
              <>
                <button onClick={goUp} className={btn} title="Up one level" aria-label="Up">
                  <FaArrowUp /> <span className="hidden sm:inline">Up</span>
                </button>
                <button onClick={createFolder} className={btn} title="Create folder" aria-label="New Folder">
                  <FaFolderPlus /> <span className="hidden sm:inline">New Folder</span>
                </button>
                <label className={`${btnPrimary} cursor-pointer`} title="Upload files" aria-label="Upload files">
                  <FaUpload /> <span className="hidden sm:inline">Upload</span>
                  <input type="file" className="sr-only" multiple onChange={upload} />
                </label>
                <label className={`${btnPrimary} cursor-pointer`} title="Upload a folder" aria-label="Upload folder">
                  <FaFolder /> <span className="hidden sm:inline">Upload Folder</span>
                  <input type="file" className="sr-only" onChange={(e) => { addFolderUploads(e.target.files); e.target.value=''; }} webkitdirectory="" directory="" />
                </label>
                <button onClick={() => loadDir(path, { force: true })} className={btn} title="Refresh" aria-label="Refresh">
                  <FaSyncAlt /> <span className="hidden sm:inline">Refresh</span>
                </button>
              </>
            );
          })()}
        </div>
      </div>
      {isDropping && (
        <div className="mb-2 text-xs text-white/70 italic">Drop files to upload…</div>
      )}
      {loading && <div className="text-white/70 text-xs">Loading…</div>}
      {err && (
        <div className="text-red-400 text-xs flex items-center gap-2">
          <span>{err}</span>
          <button onClick={() => loadDir(path, { force: true })} className="text-white/80 underline">Retry</button>
        </div>
      )}
      {(uploads.length > 0 || aggregate.inProgress) && (
        <div className="mt-2 space-y-1">
          <div className="flex items-center gap-2 bg-white/5 border border-white/10 rounded px-2 py-2">
            <div className="flex-1">
              <div className="flex justify-between text-xs text-white/80">
                <span>Uploading {uploads.length} file(s)</span>
                <span>{formatBytes(aggregate.sentBytes)} / {formatBytes(aggregate.totalBytes)}</span>
              </div>
              <div className="w-full h-2 bg-white/10 rounded mt-1 overflow-hidden">
                <div className="h-full bg-brand-500" style={{ width: `${aggregate.totalBytes ? Math.round((aggregate.sentBytes/aggregate.totalBytes)*100) : 0}%` }} />
              </div>
              {aggregate.error && <div className="text-[10px] text-red-400 mt-1">{aggregate.error}</div>}
            </div>
            {aggregate.inProgress && (
              <button className="text-white/80 hover:text-white" title="Cancel all" onClick={() => {
                Object.values(uploadAbortersRef.current).forEach((xhr) => { try { xhr.abort(); } catch {} });
                setAggregate(a => ({ ...a, inProgress: false, error: 'Cancelled' }));
              }}>
                <FaBan />
              </button>
            )}
            {!aggregate.inProgress && uploads.length > 0 && (
              <button className="text-white/80 hover:text-white" title="Clear" onClick={() => { setUploads([]); setAggregate({ totalBytes: 0, sentBytes: 0, inProgress: false, error: '' }); }}>
                <FaTimes />
              </button>
            )}
          </div>
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
                      onClick={() => downloadItem(it.name, true)}
                      className="rounded bg-white/10 hover:bg-white/20 px-2 py-1"
                    >
                      Download
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
                    <button
                      onClick={() => downloadItem(it.name, false)}
                      className="rounded bg-white/10 hover:bg-white/20 px-2 py-1"
                    >
                      Download
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


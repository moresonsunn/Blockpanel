import React, { useEffect, useMemo, useState } from 'react';
import { FaFolder, FaUpload, FaSave, FaEdit } from 'react-icons/fa';

const API = 'http://localhost:8000';

export default function FilesPanelWrapper({ serverName, isBlockedFile, onEditStart, onBlockedFileError }) {
  const [path, setPath] = useState('.');
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const [blockedFileErrorLocal, setBlockedFileErrorLocal] = useState('');
  const [renameTarget, setRenameTarget] = useState(null);
  const [renameValue, setRenameValue] = useState('');

  useEffect(() => {
    loadDir('.');
  }, [serverName]);

  async function loadDir(p = path) {
    setLoading(true);
    setErr('');
    try {
      const r = await fetch(
        `${API}/servers/${encodeURIComponent(serverName)}/files?path=${encodeURIComponent(p)}`
      );
      const d = await r.json();
      setItems(d.items || []);
      setPath(p);
    } catch (e) {
      setErr(String(e));
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
    loadDir(path);
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
    loadDir(path);
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
    loadDir(path);
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
    loadDir(path);
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
    loadDir(path);
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
    loadDir(path);
  }

  const sortedItems = useMemo(() => {
    return [...items].sort((a, b) => {
      if (a.is_dir && !b.is_dir) return -1;
      if (!a.is_dir && b.is_dir) return 1;
      return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' });
    });
  }, [items]);

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
        </div>
      </div>
      {loading && <div className="text-white/70 text-xs">Loading…</div>}
      {err && <div className="text-red-400 text-xs">{err}</div>}
      {blockedFileErrorLocal && <div className="text-red-400 text-xs">{blockedFileErrorLocal}</div>}
      {!loading && (
        <div className="space-y-1">
          {sortedItems.map((it) => (
            <div
              key={it.name}
              className="flex items-center justify-between bg-white/5 border border-white/10 rounded px-2 py-1"
              style={{ minHeight: 32 }}
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
          ))}
        </div>
      )}
    </div>
  );
}


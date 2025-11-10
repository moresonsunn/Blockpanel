import React, { useEffect, useState, useRef } from 'react';
import { API } from '../../lib/api';
/* eslint-disable */
export default function PlayersPanel({ serverId, serverName }) {
  // Defensive: normalize serverName to avoid ReferenceError if caller omits prop
  const sName = serverName || '';
  const [online, setOnline] = useState([]);
  const [offline, setOffline] = useState([]);
  const [method, setMethod] = useState('');
  const [loading, setLoading] = useState(true);
  const [playerName, setPlayerName] = useState('');
  const [reason, setReason] = useState('');
  const [rconHintDismissed, setRconHintDismissed] = useState(() => {
    try { return localStorage.getItem('rcon_hint_dismissed') === '1'; } catch { return false; }
  });
  const avatarCache = useRef({});

  async function fetchRoster() {
    try {
  if (!sName) { setPlayers([]); setMethod('missing'); return; }
  const r = await fetch(`${API}/players/${encodeURIComponent(sName)}/roster`);
      if (!r.ok) {
        setOnline([]);
        setOffline([]);
        setMethod('error');
        return;
      }
      const d = await r.json();
      if (d && typeof d === 'object') {
        setOnline(Array.isArray(d.online) ? d.online : []);
        setOffline(Array.isArray(d.offline) ? d.offline : []);
        setMethod(d.method || 'unknown');
      }
    } catch (e) {
      setOnline([]);
      setOffline([]);
      setMethod('error');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    async function load() {
      await fetchRoster();
    }
    load();
    const itv = setInterval(load, 3000);
    return () => { active = false; clearInterval(itv); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverId, serverName]);

  async function getAvatar(player) {
    if (!player) return null;
    if (avatarCache.current[player]) return avatarCache.current[player];
    try {
      const r = await fetch(`https://api.mojang.com/users/profiles/minecraft/${encodeURIComponent(player)}`);
      if (!r.ok) { avatarCache.current[player] = null; return null; }
      const jd = await r.json();
      const uuid = jd.id;
      const url = `https://crafatar.com/avatars/${uuid}?size=64&overlay=true`;
      avatarCache.current[player] = url;
      return url;
    } catch (e) {
      avatarCache.current[player] = null;
      return null;
    }
  }

  useEffect(() => {
    let canceled = false;
    (async () => {
      const all = [...online, ...offline.map(o => o.name)];
      for (const p of all) {
        if (canceled) return;
        if (!avatarCache.current[p]) {
          await getAvatar(p).catch(() => null);
        }
      }
    })();
    return () => { canceled = true; };
  }, [online, offline]);

  async function call(endpoint, method = 'POST', body = null) {
  if (!sName) return;
  await fetch(`${API}/players/${encodeURIComponent(sName)}/${endpoint}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  async function postAction(action, player, reasonArg = '') {
    try {
  if (!sName) return;
  await fetch(`${API}/players/${encodeURIComponent(sName)}/${action}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ player_name: player, action_type: action, reason: reasonArg })
      });
      await fetchRoster();
    } catch (e) {
      console.error('action error', e);
    }
  }

  async function deop(player) {
    try {
  if (!sName) return;
  await fetch(`${API}/players/${encodeURIComponent(sName)}/op/${encodeURIComponent(player)}`, { method: 'DELETE' });
      await fetchRoster();
    } catch (e) { console.error(e); }
  }

  async function sendTell(player) {
    const msg = window.prompt(`Message to ${player}`);
    if (!msg) return;
    try {
  await fetch(`${API}/servers/${serverId}/command`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command: `tell ${player} ${msg}` }) });
    } catch (e) { console.error(e); }
  }

  return (
    <div className="p-4 bg-black/20 rounded-lg space-y-4" style={{ minHeight: 300 }}>
      <div className="flex items-center justify-between">
        <div className="text-sm text-white/70">Player Management</div>
        <div className="text-xs text-white/50">Updated every 3s</div>
      </div>

      <div>
        <div className="text-xs text-white/60 mb-2">Online Players {online.length > 0 ? `(${online.length})` : ''} {method ? ` — ${method}` : ''}</div>
        {loading ? <div className="text-xs text-white/50">Loading…</div> : null}

        {online.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {online.map(p => (
              <div key={p} className="bg-white/5 border border-white/10 rounded p-3 flex items-center justify-between hover:shadow-lg transition">
                <div className="flex items-center gap-3">
                  {avatarCache.current[p] ? (
                    <img src={avatarCache.current[p]} alt={p} className="w-12 h-12 rounded-full" />
                  ) : (
                    <div className="w-12 h-12 rounded-full bg-brand-600 flex items-center justify-center text-base font-semibold text-white">{p.slice(0,1).toUpperCase()}</div>
                  )}
                  <div>
                    <div className="text-sm text-white font-semibold">{p}</div>
                    <div className="text-xs text-white/60">{serverName}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button title="Message" onClick={() => sendTell(p)} className="px-2 py-1 bg-white/5 rounded text-xs text-sky-300 hover:bg-white/10">Message</button>
                  <button title="De-OP" onClick={() => deop(p)} className="px-2 py-1 bg-white/5 rounded text-xs text-orange-300 hover:bg-white/10">DEOP</button>
                  <button title="OP" onClick={() => postAction('op', p)} className="px-2 py-1 bg-white/5 rounded text-xs text-green-300 hover:bg-white/10">OP</button>
                  <button title="Kick" onClick={() => postAction('kick', p)} className="px-2 py-1 bg-yellow-800 rounded text-xs text-yellow-100 hover:bg-yellow-700">Kick</button>
                  <button title="Ban" onClick={() => postAction('ban', p)} className="px-2 py-1 bg-red-800 rounded text-xs text-red-100 hover:bg-red-700">Ban</button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-xs text-white/50">No players online.</div>
        )}
      </div>

      <div className="pt-4">
        <div className="text-xs text-white/60 mb-2">Offline Players {offline.length ? `(${offline.length})` : ''}</div>
        {offline.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {offline.map(o => (
              <div key={o.name} className="bg-white/3 border border-white/6 rounded p-3 flex items-center justify-between opacity-90">
                <div className="flex items-center gap-3">
                  {avatarCache.current[o.name] ? (
                    <img src={avatarCache.current[o.name]} alt={o.name} className="w-10 h-10 rounded-full" />
                  ) : (
                    <div className="w-10 h-10 rounded-full bg-gray-600 flex items-center justify-center text-sm font-semibold text-white">{o.name.slice(0,1).toUpperCase()}</div>
                  )}
                  <div>
                    <div className="text-sm text-white">{o.name}</div>
                    <div className="text-xs text-white/50">{o.last_seen ? new Date(o.last_seen * 1000).toLocaleString() : 'seen recently'}</div>
                  </div>
                </div>
                <div className="text-xs text-white/40">offline</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-xs text-white/50">No known offline players yet.</div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <input className="rounded bg-gray-800 border border-white/20 px-3 py-2 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-500" placeholder="Player name" value={playerName} onChange={e => setPlayerName(e.target.value)} />
        <input className="rounded bg-gray-800 border border-white/20 px-3 py-2 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-500" placeholder="Reason (optional)" value={reason} onChange={e => setReason(e.target.value)} />
        <div className="flex items-center gap-2">
          <button onClick={() => call('whitelist', 'POST', { player_name: playerName, reason })} className="rounded bg-slate-600 hover:bg-slate-500 px-3 py-2 text-sm">Whitelist</button>
          <button onClick={() => call('ban', 'POST', { player_name: playerName, reason })} className="rounded bg-red-600 hover:bg-red-500 px-3 py-2 text-sm">Ban</button>
          <button onClick={() => call('kick', 'POST', { player_name: playerName, reason })} className="rounded bg-yellow-600 hover:bg-yellow-500 px-3 py-2 text-sm">Kick</button>
          <button onClick={() => call('op', 'POST', { player_name: playerName, reason })} className="rounded bg-green-600 hover:bg-green-500 px-3 py-2 text-sm">OP</button>
        </div>
      </div>
    </div>
  );
}

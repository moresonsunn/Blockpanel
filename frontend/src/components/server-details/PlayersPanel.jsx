import React, { useEffect, useState, useRef } from 'react';
import { API } from '../../lib/api';
/* eslint-disable */
export default function PlayersPanel({ serverId, serverName }) {
  // Defensive: normalize serverName to avoid ReferenceError if caller omits prop
  const sName = serverName || '';
  const [players, setPlayers] = useState([]);
  const [inferred, setInferred] = useState([]);
  const [method, setMethod] = useState('');
  const [loading, setLoading] = useState(true);
  const [playerName, setPlayerName] = useState('');
  const [reason, setReason] = useState('');
  const [rconHintDismissed, setRconHintDismissed] = useState(() => {
    try { return localStorage.getItem('rcon_hint_dismissed') === '1'; } catch { return false; }
  });
  const avatarCache = useRef({});

  async function fetchOnline() {
    try {
  if (!sName) { setPlayers([]); setMethod('missing'); return; }
  const r = await fetch(`${API}/players/${encodeURIComponent(sName)}/online`);
      if (!r.ok) {
        setPlayers([]);
        setMethod('error');
        return;
      }
      const d = await r.json();
      if (d && typeof d === 'object') {
        setPlayers(Array.isArray(d.players) ? d.players : []);
        setMethod(d.method || 'unknown');
      }
    } catch (e) {
      setPlayers([]);
      setMethod('error');
    } finally {
      setLoading(false);
    }
  }

  async function fetchFallbackLogs() {
    try {
  // logs are keyed by container id; serverId may be used instead of name
  const lr = await fetch(`${API}/servers/${serverId}/logs?tail=400`);
      if (!lr.ok) return;
      const ld = await lr.json();
      const text = ld.logs || '';
      const lines = text.split(/\r?\n/).reverse();
      const seen = new Set();
      const inferredList = [];
      for (const line of lines) {
        if (!line) continue;
        const m = line.match(/([A-Za-z0-9_\-]+) joined the game/i) || line.match(/([A-Za-z0-9_\-]+) logged in/i);
        if (m && m[1]) {
          const n = m[1];
          if (!seen.has(n)) { seen.add(n); inferredList.push(n); }
        }
        if (inferredList.length >= 30) break;
      }
      setInferred(inferredList.reverse());
    } catch (e) {
      setInferred([]);
    }
  }

  useEffect(() => {
    let active = true;
    async function load() {
      await fetchOnline();
      if (!active) return;
      if (players.length === 0) {
        await fetchFallbackLogs();
      } else {
        setInferred([]);
      }
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
      const all = [...players, ...inferred];
      for (const p of all) {
        if (canceled) return;
        if (!avatarCache.current[p]) {
          await getAvatar(p).catch(() => null);
        }
      }
    })();
    return () => { canceled = true; };
  }, [players, inferred]);

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
      await fetchOnline();
    } catch (e) {
      console.error('action error', e);
    }
  }

  async function deop(player) {
    try {
  if (!sName) return;
  await fetch(`${API}/players/${encodeURIComponent(sName)}/op/${encodeURIComponent(player)}`, { method: 'DELETE' });
      await fetchOnline();
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
        <div className="text-xs text-white/60 mb-2">Online Players {players.length > 0 ? `(${players.length})` : (inferred.length ? `(inferred ${inferred.length})` : '')} {method ? ` — ${method}` : ''}</div>
        {loading ? <div className="text-xs text-white/50">Loading…</div> : null}

        {!rconHintDismissed && players.length === 0 && inferred.length > 0 && (
          <div className="mb-3 p-3 bg-yellow-900/20 border border-yellow-800 rounded flex items-start justify-between">
            <div className="text-sm text-yellow-200">Your server does not expose an authoritative player list. Enable RCON (ENABLE_RCON=true and set RCON_PASSWORD) and map the RCON port to let Blockpanel manage players reliably.</div>
            <button onClick={() => { try { localStorage.setItem('rcon_hint_dismissed','1'); } catch {} setRconHintDismissed(true); }} className="ml-3 px-2 py-1 bg-yellow-800 rounded text-sm">Dismiss</button>
          </div>
        )}

        {players.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {players.map(p => (
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
        ) : inferred.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {inferred.map(p => (
              <div key={p} className="bg-white/3 border border-white/6 rounded p-3 flex items-center justify-between opacity-90">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-full bg-gray-600 flex items-center justify-center text-base font-semibold text-white">{p.slice(0,1).toUpperCase()}</div>
                  <div>
                    <div className="text-sm text-white">{p}</div>
                    <div className="text-xs text-white/50">(inferred)</div>
                  </div>
                </div>
                <div className="text-xs text-white/40">from logs</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-xs text-white/50">No players online.</div>
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

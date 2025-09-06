import React, { useEffect, useMemo, useState } from 'react';
import { API } from '../../lib/api';

export default function PlayersPanel({ serverId, serverName }) {
  const [playerName, setPlayerName] = useState('');
  const [reason, setReason] = useState('');
  const [players, setPlayers] = useState([]);

  // Poll server resources for player names
  useEffect(() => {
    let active = true;
    let interval = null;
    async function load() {
      try {
        const r = await fetch(`${API}/servers/${serverId}/resources`);
        if (!r.ok) return;
        const d = await r.json();
        if (!active) return;
        const names = Array.isArray(d?.players?.names) ? d.players.names : [];
        setPlayers(names);
      } catch {
        if (active) setPlayers([]);
      }
    }
    load();
    interval = setInterval(load, 8000);
    return () => { active = false; if (interval) clearInterval(interval); };
  }, [serverId]);

  async function call(endpoint, method = 'POST', body = null) {
    await fetch(`${API}/players/${encodeURIComponent(serverName)}/${endpoint}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  return (
    <div className="p-4 bg-black/20 rounded-lg space-y-4">
      <div className="text-sm text-white/70">Player Management</div>
      {players.length > 0 ? (
        <div>
          <div className="text-xs text-white/60 mb-2">Online Players ({players.length})</div>
          <div className="flex flex-wrap gap-2">
            {players.map(p => (
              <div key={p} className="bg-white/10 border border-white/10 rounded px-2 py-1 text-xs flex items-center gap-2">
                <span>{p}</span>
                <button onClick={() => call('kick', 'POST', { player_name: p, reason: reason || 'Kicked by admin' })} className="text-yellow-300 hover:text-yellow-200">Kick</button>
                <button onClick={() => call('ban', 'POST', { player_name: p, reason: reason || 'Banned by admin' })} className="text-red-300 hover:text-red-200">Ban</button>
                <button onClick={() => call('op', 'POST', { player_name: p })} className="text-green-300 hover:text-green-200">OP</button>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="text-xs text-white/50">No players online.</div>
      )}

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

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { FaTerminal, FaFilter, FaPlus, FaTimes } from 'react-icons/fa';
import { API } from '../lib/api';
import { loadMuteConfig, saveMuteConfig, defaultMuteRegexes, defaultMutePatterns } from '../lib/consoleFilters';
import { ansiToHtml } from '../lib/ansiToHtml';

export default function TerminalPanel({ containerId, resetToken = 0 }) {
  const [cmd, setCmd] = useState('');
  const [rawLogs, setRawLogs] = useState('');
  const [showSettings, setShowSettings] = useState(false);
  const [muteEnabled, setMuteEnabled] = useState(true);
  const [patternsText, setPatternsText] = useState(defaultMutePatterns.join('\n'));
  const [showColors, setShowColors] = useState(true);
  const scrollRef = useRef(null);

  // Load persisted config per server (container)
  useEffect(() => {
    if (!containerId) return;
    const cfg = loadMuteConfig(containerId);
    setMuteEnabled(cfg.enabled);
    setPatternsText(cfg.patterns.join('\n'));
  }, [containerId]);

  // Persist on changes
  useEffect(() => {
    if (!containerId) return;
    const patterns = patternsText
      .split(/\r?\n/)
      .map(s => s.trim())
      .filter(Boolean);
    saveMuteConfig(containerId, { enabled: muteEnabled, patterns });
  }, [containerId, muteEnabled, patternsText]);

  // Initial fetch and fetch on reset (start/stop/restart)
  useEffect(() => {
    if (!containerId) return;
    let active = true;
    setRawLogs('');
    fetch(`${API}/servers/${containerId}/logs?tail=200`)
      .then((r) => r.json())
      .then((d) => {
        if (active && d && typeof d.logs === 'string') setRawLogs(d.logs);
      })
      .catch(() => {
        if (active) setRawLogs('');
      });
    return () => { active = false; };
  }, [containerId, resetToken]);

  // Polling
  useEffect(() => {
    if (!containerId) return;
    let active = true;
    let interval = null;
    async function pollLogs() {
      try {
        const r = await fetch(`${API}/servers/${containerId}/logs?tail=200`);
        const d = await r.json();
        if (active && d && typeof d.logs === 'string') setRawLogs(d.logs);
      } catch (e) {
        if (active) setRawLogs('');
      }
    }
    interval = setInterval(pollLogs, 4000);
    return () => { active = false; if (interval) clearInterval(interval); };
  }, [containerId]);

  // Compile regex safely
  const compiledRegexes = useMemo(() => {
    const userPatterns = patternsText
      .split(/\r?\n/)
      .map(s => s.trim())
      .filter(Boolean);
    const patterns = userPatterns.length ? userPatterns : defaultMutePatterns;
    const out = [];
    for (const p of patterns) {
      try {
        out.push(new RegExp(p, 'i'));
      } catch {
        // ignore invalid patterns
      }
    }
    return out.length ? out : defaultMuteRegexes;
  }, [patternsText]);

  const filteredLogs = useMemo(() => {
    if (!muteEnabled) return rawLogs;
    if (!rawLogs) return rawLogs;
    const lines = rawLogs.split(/\r?\n/);
    const kept = lines.filter(line => !compiledRegexes.some(rx => rx.test(line)));
    return kept.join('\n');
  }, [rawLogs, muteEnabled, compiledRegexes]);

  const renderedHtml = useMemo(() => {
    const text = filteredLogs || '';
    return showColors ? ansiToHtml(text) : ansiToHtml(text.replace(/\x1b\[[0-9;]*m/g, ''));
  }, [filteredLogs, showColors]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [filteredLogs]);

  function send() {
    if (!cmd.trim()) return;
    fetch(`${API}/servers/${containerId}/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: cmd }),
    });
    setCmd('');
  }

  return (
    <div className="p-6 bg-black/20 rounded-lg space-y-4" style={{ minHeight: 600 }}>
      <div className="flex items-center justify-between">
        <div className="text-base text-white/70 mb-2">Server Console & Logs (live)</div>
        <div className="flex items-center gap-2">
          <label className="inline-flex items-center gap-2 text-sm text-white/70">
            <input
              type="checkbox"
              checked={showColors}
              onChange={(e) => setShowColors(e.target.checked)}
            />
            Show colors
          </label>
          <label className="inline-flex items-center gap-2 text-sm text-white/70">
            <input
              type="checkbox"
              checked={muteEnabled}
              onChange={(e) => setMuteEnabled(e.target.checked)}
            />
            Mute patterns
          </label>
          <button
            onClick={() => setShowSettings(v => !v)}
            className="inline-flex items-center gap-2 rounded-md bg-white/10 hover:bg-white/20 px-3 py-1.5 text-sm"
            title="Manage mute patterns"
          >
            <FaFilter /> Manage
          </button>
        </div>
      </div>

      {showSettings && (
        <div className="bg-white/5 border border-white/10 rounded p-3 space-y-2">
          <div className="text-xs text-white/60">One regex per line (case-insensitive). Invalid patterns are ignored.</div>
          <textarea
            className="w-full h-24 rounded bg-black/40 border border-white/10 p-2 text-xs"
            value={patternsText}
            onChange={(e) => setPatternsText(e.target.value)}
          />
          <div className="text-xs text-white/50">Defaults include common player count lines.</div>
        </div>
      )}

      <div
        ref={scrollRef}
        className="text-xs text-white/70 whitespace-pre-wrap bg-black/30 p-4 rounded max-h-[800px] min-h-[500px] overflow-auto font-mono"
        style={{ fontSize: '0.75rem', lineHeight: '1.25', height: 500 }}
        dangerouslySetInnerHTML={{ __html: renderedHtml || '<span class="text-white/40">No output yet.</span>' }}
      />

      <div className="flex gap-3 mt-2">
        <input
          value={cmd}
          onChange={(e) => setCmd(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          className="flex-1 rounded-md bg-white/5 border border-white/10 px-4 py-3 text-base"
          placeholder="Type a command (e.g. say hello or op Username)"
        />
        <button
          onClick={send}
          className="inline-flex items-center gap-2 rounded-md bg-brand-500 hover:bg-brand-400 px-4 py-3 font-semibold text-base"
        >
          <FaTerminal /> Send
        </button>
      </div>
    </div>
  );
}

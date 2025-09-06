export const defaultMutePatterns = [
  '^There are \\d+ of a max of \\d+ players online:?',
  'max player count is \\d+',
  '^Players? online: \\d+(?:/\\d+)?',
  '^list:.*',
];

export const defaultMuteRegexes = defaultMutePatterns.map(p => new RegExp(p, 'i'));

const KEY_PREFIX = 'consoleMute.';

export function loadMuteConfig(serverId) {
  try {
    const raw = localStorage.getItem(KEY_PREFIX + serverId);
    if (!raw) return { enabled: true, patterns: defaultMutePatterns };
    const obj = JSON.parse(raw);
    if (!obj || typeof obj !== 'object') return { enabled: true, patterns: defaultMutePatterns };
    return {
      enabled: typeof obj.enabled === 'boolean' ? obj.enabled : true,
      patterns: Array.isArray(obj.patterns) && obj.patterns.length ? obj.patterns : defaultMutePatterns,
    };
  } catch {
    return { enabled: true, patterns: defaultMutePatterns };
  }
}

export function saveMuteConfig(serverId, { enabled, patterns }) {
  try {
    localStorage.setItem(KEY_PREFIX + serverId, JSON.stringify({ enabled: !!enabled, patterns: Array.isArray(patterns) ? patterns : defaultMutePatterns }));
  } catch {
    // ignore
  }
}

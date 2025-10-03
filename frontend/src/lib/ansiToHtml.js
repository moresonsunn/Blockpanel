// Minimal, safe ANSI -> HTML converter supporting SGR colors (incl. 24-bit truecolor)
// - Handles: reset (0), bold (1/22), italic (3/23), underline (4/24)
// - Foreground: 30-37, 90-97, 39 (default), 38;2;r;g;b (truecolor)
// - Background: 40-47, 100-107, 49 (default), 48;2;r;g;b (truecolor)
// Any other SGR codes are ignored. Output HTML is escaped except for ANSI-derived spans.

function clampByte(n) {
  n = Number(n);
  if (!Number.isFinite(n)) return 0;
  if (n < 0) return 0;
  if (n > 255) return 255;
  return Math.floor(n);
}

function escHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

const BASIC_FG = {
  30: '#000000',
  31: '#aa0000',
  32: '#00aa00',
  33: '#aa5500',
  34: '#0000aa',
  35: '#aa00aa',
  36: '#00aaaa',
  37: '#aaaaaa',
  90: '#555555',
  91: '#ff5555',
  92: '#55ff55',
  93: '#ffff55',
  94: '#5555ff',
  95: '#ff55ff',
  96: '#55ffff',
  97: '#ffffff',
};

const BASIC_BG = {
  40: '#000000',
  41: '#aa0000',
  42: '#00aa00',
  43: '#aa5500',
  44: '#0000aa',
  45: '#aa00aa',
  46: '#00aaaa',
  47: '#aaaaaa',
  100: '#555555',
  101: '#ff5555',
  102: '#55ff55',
  103: '#ffff55',
  104: '#5555ff',
  105: '#ff55ff',
  106: '#55ffff',
  107: '#ffffff',
};

function styleToAttr(style) {
  const parts = [];
  if (style.color) parts.push(`color: ${style.color}`);
  if (style.backgroundColor) parts.push(`background-color: ${style.backgroundColor}`);
  if (style.fontWeight) parts.push(`font-weight: ${style.fontWeight}`);
  if (style.fontStyle) parts.push(`font-style: ${style.fontStyle}`);
  if (style.textDecoration) parts.push(`text-decoration: ${style.textDecoration}`);
  return parts.length ? ` style="${parts.join('; ')}"` : '';
}

function applySgrCodes(style, codes) {
  let i = 0;
  while (i < codes.length) {
    const code = Number(codes[i] || 0);
    if (code === 0) {
      // reset
      style.color = undefined;
      style.backgroundColor = undefined;
      style.fontWeight = undefined;
      style.fontStyle = undefined;
      style.textDecoration = undefined;
      i += 1;
      continue;
    }
    if (code === 1) { style.fontWeight = 'bold'; i += 1; continue; }
    if (code === 22) { style.fontWeight = undefined; i += 1; continue; }
    if (code === 3) { style.fontStyle = 'italic'; i += 1; continue; }
    if (code === 23) { style.fontStyle = undefined; i += 1; continue; }
    if (code === 4) { style.textDecoration = 'underline'; i += 1; continue; }
    if (code === 24) { style.textDecoration = undefined; i += 1; continue; }

    // Basic foreground/background
    if (BASIC_FG[code]) { style.color = BASIC_FG[code]; i += 1; continue; }
    if (BASIC_BG[code]) { style.backgroundColor = BASIC_BG[code]; i += 1; continue; }
    if (code === 39) { style.color = undefined; i += 1; continue; }
    if (code === 49) { style.backgroundColor = undefined; i += 1; continue; }

    // Truecolor foreground: 38;2;r;g;b
    if (code === 38 && codes[i + 1] === '2' && codes.length >= i + 5) {
      const r = clampByte(codes[i + 2]);
      const g = clampByte(codes[i + 3]);
      const b = clampByte(codes[i + 4]);
      style.color = `rgb(${r}, ${g}, ${b})`;
      i += 5;
      continue;
    }
    // Truecolor background: 48;2;r;g;b
    if (code === 48 && codes[i + 1] === '2' && codes.length >= i + 5) {
      const r = clampByte(codes[i + 2]);
      const g = clampByte(codes[i + 3]);
      const b = clampByte(codes[i + 4]);
      style.backgroundColor = `rgb(${r}, ${g}, ${b})`;
      i += 5;
      continue;
    }
    // Skip unsupported/other extended codes gracefully
    i += 1;
  }
}

export function ansiToHtml(input) {
  if (!input) return '';
  const re = /\x1b\[([0-9;]*)m/g; // CSI ... m
  let result = '';
  let lastIndex = 0;
  const style = {};

  let m;
  while ((m = re.exec(input)) !== null) {
    const chunk = input.slice(lastIndex, m.index);
    if (chunk) {
      const safe = escHtml(chunk);
      const attr = styleToAttr(style);
      if (attr) result += `<span${attr}>${safe}</span>`;
      else result += safe;
    }
    const params = m[1] ? m[1].split(';') : ['0'];
    applySgrCodes(style, params);
    lastIndex = re.lastIndex;
  }

  if (lastIndex < input.length) {
    const tail = input.slice(lastIndex);
    const safe = escHtml(tail);
    const attr = styleToAttr(style);
    if (attr) result += `<span${attr}>${safe}</span>`;
    else result += safe;
  }

  return result;
}

export function stripAnsi(input) {
  if (!input) return '';
  return input.replace(/\x1b\[[0-9;]*m/g, '');
}

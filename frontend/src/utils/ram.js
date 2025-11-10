// RAM normalization utility extracted for reuse across forms.
// Converts inputs like "2048M", "2G", "2GB", "2048" into canonical MB string e.g. "2048M".
// Returns empty string on invalid input.
export function normalizeRamInput(value, { defaultUnit = 'M', clampMin = 16, clampMax = 1048576 } = {}) {
  if (value == null) return '';
  let raw = String(value).trim();
  if (!raw) return '';
  raw = raw.replace(/[, ]+/g, '');
  const pureNumber = /^\d+(?:\.\d+)?$/.test(raw);
  let num = 0;
  let unit = defaultUnit;
  if (pureNumber) {
    num = parseFloat(raw);
  } else {
    const m = raw.match(/^(\d+(?:\.\d+)?)([kmgtp]?)(?:i?b?)$/i);
    if (!m) return '';
    num = parseFloat(m[1]);
    unit = m[2] ? m[2].toUpperCase() : defaultUnit.toUpperCase();
  }
  if (!isFinite(num) || num <= 0) return '';
  const factorMap = { K: 1/1024, M: 1, G: 1024, T: 1024*1024, P: 1024*1024*1024 };
  const factor = factorMap[unit] || 1;
  let mb = num * factor;
  mb = Math.round(Math.min(Math.max(mb, clampMin), clampMax));
  return mb + 'M';
}

// Simple validator that ensures min <= max
export function validateRamRange(minValue, maxValue) {
  const min = normalizeRamInput(minValue);
  const max = normalizeRamInput(maxValue);
  if (!min || !max) return { ok: false, error: 'Invalid RAM value.' };
  const toMB = (v) => parseInt(v.replace(/m$/i, ''), 10);
  if (toMB(min) > toMB(max)) return { ok: false, error: 'Min RAM cannot exceed Max RAM.' };
  return { ok: true, min, max };
}

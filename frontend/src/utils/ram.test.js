import { normalizeRamInput, validateRamRange } from './ram';

describe('normalizeRamInput', () => {
  test('raw MB number', () => {
    expect(normalizeRamInput('2048')).toBe('2048M');
  });
  test('gigabytes integer', () => {
    expect(normalizeRamInput('2G')).toBe('2048M');
  });
  test('gigabytes with GB suffix', () => {
    expect(normalizeRamInput('2GB')).toBe('2048M');
  });
  test('decimal gigabytes rounds', () => {
    expect(normalizeRamInput('1.5G')).toBe('1536M');
  });
  test('invalid string', () => {
    expect(normalizeRamInput('abc')).toBe('');
  });
});

describe('validateRamRange', () => {
  test('valid order', () => {
    const r = validateRamRange('1024M', '2G');
    expect(r.ok).toBe(true);
    expect(r.min).toBe('1024M');
    expect(r.max).toBe('2048M');
  });
  test('invalid order', () => {
    const r = validateRamRange('4G', '2G');
    expect(r.ok).toBe(false);
  });
});

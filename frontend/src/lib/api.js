// Prefer same-origin '/api' to avoid CORS in proxied environments (CasaOS, reverse proxies).
// If REACT_APP_API_URL is set, it takes precedence (can be absolute or relative).
const _defaultApi = (typeof window !== 'undefined') ? '/api' : 'http://localhost:8000';
export const API = process.env.REACT_APP_API_URL || _defaultApi;

const TOKEN_KEY = 'auth_token';
export const getStoredToken = () => localStorage.getItem(TOKEN_KEY) || '';
export const setStoredToken = (t) => localStorage.setItem(TOKEN_KEY, t);
export const clearStoredToken = () => localStorage.removeItem(TOKEN_KEY);
export const authHeaders = () => {
  const t = getStoredToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
};

export const API = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const TOKEN_KEY = 'auth_token';
export const getStoredToken = () => localStorage.getItem(TOKEN_KEY) || '';
export const setStoredToken = (t) => localStorage.setItem(TOKEN_KEY, t);
export const clearStoredToken = () => localStorage.removeItem(TOKEN_KEY);
export const authHeaders = () => {
  const t = getStoredToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
};

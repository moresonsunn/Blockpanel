// Centralized branding configuration for the frontend.
// Allows overriding via build-time env: REACT_APP_APP_NAME
// Falls back to Lynx if unspecified.

export const APP_NAME = process.env.REACT_APP_APP_NAME || 'Lynx';

export function applyDocumentBranding() {
  if (typeof document !== 'undefined') {
    const base = APP_NAME;
    if (!document.title || !document.title.includes(base)) {
      document.title = base;
    }
  }
}

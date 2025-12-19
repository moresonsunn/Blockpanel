import React, { useMemo, useState } from 'react';
import { FaLock } from 'react-icons/fa';

function validateNewPassword(password) {
  if (!password || password.length < 8) return 'Password must be at least 8 characters long.';
  if (!/[A-Z]/.test(password)) return 'Password must contain at least one uppercase letter.';
  if (!/[a-z]/.test(password)) return 'Password must contain at least one lowercase letter.';
  if (!/[0-9]/.test(password)) return 'Password must contain at least one digit.';
  return '';
}

export default function MustChangePasswordPage({ appName, apiBaseUrl, onComplete, onLogout }) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const passwordHint = useMemo(() => validateNewPassword(newPassword), [newPassword]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    const strengthError = validateNewPassword(newPassword);
    if (strengthError) {
      setError(strengthError);
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('New password and confirmation do not match.');
      return;
    }

    setLoading(true);
    try {
      const r = await fetch(`${apiBaseUrl}/auth/me/password`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      if (!r.ok) {
        const payload = await r.json().catch(() => null);
        throw new Error((payload && (payload.detail || payload.message)) || `HTTP ${r.status}`);
      }
      onComplete();
    } catch (err) {
      setError(err.message || 'Password change failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-ink bg-hero-gradient flex w-full">
      <div className="min-h-screen flex items-center justify-center w-full">
        <div className="max-w-md w-full mx-4">
          <div className="rounded-xl glassmorphism-strong p-6 space-y-4 animate-fade-in">
            <div className="text-center mb-2 animate-slide-up">
              <div className="w-16 h-16 bg-brand-500 rounded-full flex items-center justify-center mx-auto mb-4 shadow-card">
                <FaLock className="text-2xl text-white" />
              </div>
              <h1 className="text-2xl font-bold text-white">{appName}</h1>
              <p className="text-white/70 mt-2">Password change required</p>
              <p className="text-xs text-white/50 mt-1">
                For security, you must set a new password before continuing.
              </p>
            </div>

            {error && (
              <div className="bg-red-500/10 border border-red-500/20 text-red-300 p-3 rounded-lg text-sm animate-slide-up">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4 animate-slide-up-delayed">
              <div>
                <label className="block text-sm font-medium text-white/70 mb-2">Current password</label>
                <input
                  type="password"
                  className="w-full rounded-md bg-white/5 border border-white/10 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-brand-500 text-white placeholder-white/50"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-white/70 mb-2">New password</label>
                <input
                  type="password"
                  className="w-full rounded-md bg-white/5 border border-white/10 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-brand-500 text-white placeholder-white/50"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                  autoComplete="new-password"
                />
                {passwordHint && !error && (
                  <div className="text-xs text-white/50 mt-2">{passwordHint}</div>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-white/70 mb-2">Confirm new password</label>
                <input
                  type="password"
                  className="w-full rounded-md bg-white/5 border border-white/10 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-brand-500 text-white placeholder-white/50"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  autoComplete="new-password"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 rounded-md bg-brand-500 hover:bg-brand-600 disabled:opacity-50 text-white font-medium transition-colors hover-lift"
              >
                {loading ? 'Updating...' : 'Update Password'}
              </button>

              <button
                type="button"
                onClick={onLogout}
                className="w-full py-2 rounded-md bg-white/10 hover:bg-white/20 text-white/80 transition-colors"
              >
                Sign out
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}

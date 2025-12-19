import React, { useMemo } from 'react';
import { FaServer } from 'react-icons/fa';

const DISCORD_INVITE_URL = 'https://discord.gg/ap77trGq8r';

function OrbitLink({ className, style, children }) {
  return (
    <div className={className} style={style} aria-hidden={false}>
      <a
        href={DISCORD_INVITE_URL}
        target="_blank"
        rel="noreferrer"
        className="pointer-events-auto inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs text-white/80 hover:bg-white/10 hover:text-white transition-colors"
      >
        {children}
      </a>
    </div>
  );
}

export default function LoginPage({
  appName,
  username,
  password,
  onUsernameChange,
  onPasswordChange,
  onSubmit,
  error,
  loading,
}) {
  const orbitRadius = useMemo(() => ({ '--orbit-radius': '160px' }), []);

  return (
    <div className="min-h-screen bg-ink bg-hero-gradient flex w-full">
      <div className="min-h-screen flex items-center justify-center w-full">
        <div className="max-w-md w-full mx-4">
          <div className="relative">
            {/* Orbiting Discord "ad" links */}
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
              <OrbitLink
                className="animate-orbit"
                style={{ ...orbitRadius, '--orbit-duration': '10s' }}
              >
                Join our Discord
              </OrbitLink>
              <OrbitLink
                className="animate-orbit-reverse"
                style={{ ...orbitRadius, '--orbit-duration': '14s', '--orbit-radius': '210px' }}
              >
                Support • Updates
              </OrbitLink>
            </div>

            <div className="rounded-xl glassmorphism-strong p-6 space-y-4 animate-fade-in">
              <div className="text-center mb-6 animate-slide-up">
                <div className="w-16 h-16 bg-brand-500 rounded-full flex items-center justify-center mx-auto mb-4 shadow-card animate-glow">
                  <FaServer className="text-2xl text-white" />
                </div>
                <h1 className="text-2xl font-bold text-white">{appName}</h1>
                <p className="text-white/70 mt-2">Please sign in to continue</p>
              </div>

              {error && (
                <div className="bg-red-500/10 border border-red-500/20 text-red-300 p-3 rounded-lg text-sm animate-slide-up">
                  {error}
                </div>
              )}

              <form onSubmit={onSubmit} className="space-y-4 animate-slide-up-delayed">
                <div>
                  <label className="block text-sm font-medium text-white/70 mb-2">Username</label>
                  <input
                    type="text"
                    className="w-full rounded-md bg-white/5 border border-white/10 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-brand-500 text-white placeholder-white/50"
                    placeholder="Enter your username"
                    value={username}
                    onChange={(e) => onUsernameChange(e.target.value)}
                    required
                    autoComplete="username"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-white/70 mb-2">Password</label>
                  <input
                    type="password"
                    className="w-full rounded-md bg-white/5 border border-white/10 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-brand-500 text-white placeholder-white/50"
                    placeholder="Enter your password"
                    value={password}
                    onChange={(e) => onPasswordChange(e.target.value)}
                    required
                    autoComplete="current-password"
                  />
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full py-3 rounded-md bg-brand-500 hover:bg-brand-600 disabled:opacity-50 text-white font-medium transition-colors hover-lift"
                >
                  {loading ? 'Signing in...' : 'Sign In'}
                </button>

                <div className="text-center text-xs text-white/50 pt-2">
                  <a
                    className="text-white/70 hover:text-white underline underline-offset-4"
                    href={DISCORD_INVITE_URL}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Join our Discord
                  </a>
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

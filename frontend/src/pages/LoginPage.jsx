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
  const sideOffset = useMemo(() => ({ '--ad-offset': 'clamp(240px, 30vw, 420px)' }), []);

  return (
    <div className="min-h-screen bg-ink bg-hero-gradient flex w-full relative overflow-hidden">
      {/* Side promos (kept away from the form; hidden on small screens) */}
      <div className="pointer-events-none absolute inset-0 z-0 hidden md:block">
        <div
          className="absolute left-1/2 top-1/2"
          style={{ ...sideOffset, transform: 'translate(calc(-50% - var(--ad-offset)), -50%)' }}
        >
          <div className="pointer-events-none" style={{ transform: 'rotate(-6deg)' }}>
            <div className="pointer-events-auto animate-float">
              <OrbitLink>
                Join our Discord
              </OrbitLink>
            </div>
          </div>
          <div className="mt-4 pointer-events-none" style={{ transform: 'rotate(4deg)' }}>
            <div className="pointer-events-auto animate-bounce-subtle">
              <OrbitLink>
                Support • Updates
              </OrbitLink>
            </div>
          </div>
        </div>

        <div
          className="absolute left-1/2 top-1/2"
          style={{ ...sideOffset, transform: 'translate(calc(-50% + var(--ad-offset)), -50%)' }}
        >
          <div className="pointer-events-none" style={{ transform: 'rotate(7deg)' }}>
            <div className="pointer-events-auto animate-float">
              <OrbitLink>
                Events • Giveaways
              </OrbitLink>
            </div>
          </div>
          <div className="mt-4 pointer-events-none" style={{ transform: 'rotate(-3deg)' }}>
            <div className="pointer-events-auto animate-bounce-subtle">
              <OrbitLink>
                Get help fast
              </OrbitLink>
            </div>
          </div>
        </div>
      </div>

      <div className="min-h-screen flex items-center justify-center w-full relative z-10">
        <div className="max-w-md w-full mx-4">
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
  );
}

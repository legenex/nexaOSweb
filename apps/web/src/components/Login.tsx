import { useState } from 'react';

import { useAuth } from '../app/AuthProvider';

// A minimal login surface for the browser companion. The desktop wrapper authenticates
// with its bearer and skips this screen. When reached from the public marketing homepage an
// onBack handler is passed so the visitor can return to the landing page.
//
// The card has two modes: the sign-in form, and a reset request form reached by the "reset
// password" link. The reset form posts an email to the Brain, which mails a single-use link; the
// confirmation is deliberately neutral so it never reveals whether an account exists.
export function Login({ onBack }: { onBack?: () => void } = {}) {
  const { login, requestPasswordReset } = useAuth();
  const [mode, setMode] = useState<'signin' | 'request'>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function switchMode(next: 'signin' | 'request') {
    setMode(next);
    setError(null);
    setNotice(null);
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch {
      setError('Invalid email or password.');
    } finally {
      setBusy(false);
    }
  }

  async function onRequestReset(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await requestPasswordReset(email);
      setNotice('If an account exists for that email, a reset link is on its way.');
    } catch {
      setError('Could not send the reset link. Please try again in a moment.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full items-center justify-center">
      <form
        onSubmit={mode === 'signin' ? onSubmit : onRequestReset}
        className="border-electric border-electric-on w-[340px] rounded-glass border border-line bg-surface/80 p-7 text-center backdrop-blur"
      >
        <div className="mono-label">{mode === 'signin' ? 'sign in' : 'reset password'}</div>
        <h1 className="mb-5 mt-1 text-2xl font-bold text-cream">NexaOS</h1>

        <label className="mono-label block text-left" htmlFor="email">
          email
        </label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          className="mb-3 mt-1 w-full rounded-lg border border-line bg-canvas px-3 py-2 text-sm text-cream outline-none focus:border-accent"
        />

        {mode === 'signin' ? (
          <>
            <label className="mono-label block text-left" htmlFor="password">
              password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mb-4 mt-1 w-full rounded-lg border border-line bg-canvas px-3 py-2 text-sm text-cream outline-none focus:border-accent"
            />
          </>
        ) : (
          <p className="mb-4 mt-1 text-sm text-muted">
            Enter your email and we will send you a link to set a new password.
          </p>
        )}

        {error ? <p className="mb-3 text-sm text-danger">{error}</p> : null}
        {notice ? <p className="mb-3 text-sm text-accent">{notice}</p> : null}

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-lg bg-accent py-2 text-sm font-semibold text-black transition hover:bg-accent-hi disabled:opacity-60"
        >
          {mode === 'signin'
            ? busy
              ? 'Signing in'
              : 'Sign in'
            : busy
              ? 'Sending'
              : 'Send reset link'}
        </button>

        <button
          type="button"
          onClick={() => switchMode(mode === 'signin' ? 'request' : 'signin')}
          className="mono-label mt-4 block w-full text-center hover:text-accent"
        >
          {mode === 'signin' ? 'reset password' : 'back to sign in'}
        </button>

        {onBack ? (
          <button
            type="button"
            onClick={onBack}
            className="mono-label mt-2 block w-full text-center hover:text-accent"
          >
            back to home
          </button>
        ) : null}
      </form>
    </div>
  );
}

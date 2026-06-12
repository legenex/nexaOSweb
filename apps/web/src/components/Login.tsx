import { useState } from 'react';

import { useAuth } from '../app/AuthProvider';

// A minimal login surface for the browser companion. The desktop wrapper authenticates
// with its bearer and skips this screen.
export function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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

  return (
    <div className="flex h-full items-center justify-center">
      <form
        onSubmit={onSubmit}
        className="w-[320px] rounded-glass border border-line bg-surface/80 p-6 backdrop-blur"
      >
        <div className="mono-label">sign in</div>
        <h1 className="mb-4 mt-1 text-xl font-semibold text-cream">nexaOSweb</h1>

        <label className="mono-label" htmlFor="email">
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

        <label className="mono-label" htmlFor="password">
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

        {error ? <p className="mb-3 text-sm text-danger">{error}</p> : null}

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-lg bg-accent py-2 text-sm font-semibold text-black transition hover:bg-accent-hi disabled:opacity-60"
        >
          {busy ? 'Signing in' : 'Sign in'}
        </button>
      </form>
    </div>
  );
}

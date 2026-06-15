import { useState } from 'react';

import { useAuth } from '../app/AuthProvider';

// The destination of the emailed reset link, shown at the #reset hash route. The raw token rides in
// the hash as #reset?token=... The user sets a new password, which the Brain validates against the
// single-use token, then they return to sign in.
//
// onDone returns to the sign-in screen; onBack (optional) returns to the marketing home.
export function ResetPassword({
  token,
  onDone,
  onBack,
}: {
  token: string;
  onDone: () => void;
  onBack?: () => void;
}) {
  const { confirmPasswordReset } = useAuth();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    if (!token) {
      setError('This reset link is missing its token. Request a new link.');
      return;
    }
    if (password.length < 8) {
      setError('Use at least 8 characters.');
      return;
    }
    if (password !== confirm) {
      setError('The two passwords do not match.');
      return;
    }

    setBusy(true);
    try {
      await confirmPasswordReset(token, password);
      setDone(true);
    } catch {
      setError('This reset link is invalid or has expired. Request a new one.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full items-center justify-center">
      <div className="w-[320px] rounded-glass border border-line bg-surface/80 p-6 backdrop-blur">
        <div className="mono-label">reset password</div>
        <h1 className="mb-4 mt-1 text-xl font-semibold text-cream">nexaOSweb</h1>

        {done ? (
          <>
            <p className="mb-4 text-sm text-cream">
              Your password has been updated. You can now sign in with it.
            </p>
            <button
              type="button"
              onClick={onDone}
              className="w-full rounded-lg bg-accent py-2 text-sm font-semibold text-black transition hover:bg-accent-hi"
            >
              Go to sign in
            </button>
          </>
        ) : (
          <form onSubmit={onSubmit}>
            <label className="mono-label" htmlFor="new-password">
              new password
            </label>
            <input
              id="new-password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mb-3 mt-1 w-full rounded-lg border border-line bg-canvas px-3 py-2 text-sm text-cream outline-none focus:border-accent"
            />

            <label className="mono-label" htmlFor="confirm-password">
              confirm password
            </label>
            <input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              className="mb-4 mt-1 w-full rounded-lg border border-line bg-canvas px-3 py-2 text-sm text-cream outline-none focus:border-accent"
            />

            {error ? <p className="mb-3 text-sm text-danger">{error}</p> : null}

            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-lg bg-accent py-2 text-sm font-semibold text-black transition hover:bg-accent-hi disabled:opacity-60"
            >
              {busy ? 'Saving' : 'Set new password'}
            </button>

            <button
              type="button"
              onClick={onDone}
              className="mono-label mt-4 block w-full text-center hover:text-accent"
            >
              back to sign in
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
        )}
      </div>
    </div>
  );
}

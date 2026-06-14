import { useCallback, useEffect, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';
import { Button, MonoLabel, Pill } from '../../components/primitives';

type UserRead = Schemas['UserRead'];
type UserRole = Schemas['UserCreate']['role'];

const ROLES: UserRole[] = ['owner', 'admin', 'member'];
const INPUT =
  'rounded-md border border-line bg-canvas px-3 py-2 text-sm text-cream outline-none focus:border-accent';

// Users: list everyone with access, create a ready to sign in account directly (email plus a
// password the owner sets), optionally invite by email, change a role, set or reset a password,
// and remove (soft delete), over the /users endpoints. Direct create is the primary path so an
// owner does not depend on an email round trip to add people.
export function UsersPanel() {
  const [users, setUsers] = useState<UserRead[] | null>(null);
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<UserRole>('member');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    const { data } = await api.GET('/users');
    setUsers((data as UserRead[]) ?? []);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const resetForm = () => {
    setEmail('');
    setName('');
    setPassword('');
    setRole('member');
  };

  const create = async () => {
    const value = email.trim();
    if (!value || password.length < 8 || busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    const { error: err } = await api.POST('/users', {
      body: { email: value, password, name: name.trim() || null, role },
    });
    if (err) {
      setError('Could not create that user. The email may already be in use.');
    } else {
      setNotice(`Created ${value}. They can sign in now.`);
      resetForm();
      await load();
    }
    setBusy(false);
  };

  const invite = async () => {
    const value = email.trim();
    if (!value || busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    const { error: err } = await api.POST('/users/invite', {
      body: { email: value, name: name.trim() || null, role },
    });
    if (err) {
      setError('Could not invite that email. It may already exist.');
    } else {
      setNotice(`Invited ${value}. Set a password for them once they appear below.`);
      resetForm();
      await load();
    }
    setBusy(false);
  };

  const changeRole = async (id: number, next: UserRole) => {
    await api.PATCH('/users/{user_id}', {
      params: { path: { user_id: id } },
      body: { role: next },
    });
    await load();
  };

  const setUserPassword = async (id: number, label: string) => {
    const next = window.prompt(`Set a new password for ${label} (at least 8 characters):`);
    if (next === null) return;
    if (next.length < 8) {
      setError('A password must be at least 8 characters.');
      return;
    }
    setError(null);
    const { error: err } = await api.PATCH('/users/{user_id}', {
      params: { path: { user_id: id } },
      body: { password: next },
    });
    if (err) {
      setError('Could not update that password.');
    } else {
      setNotice(`Password updated for ${label}.`);
      await load();
    }
  };

  const remove = async (id: number) => {
    await api.DELETE('/users/{user_id}', { params: { path: { user_id: id } } });
    await load();
  };

  if (!users) return <MonoLabel tone="faint">loading users</MonoLabel>;

  const canCreate = !!email.trim() && password.length >= 8 && !busy;

  return (
    <div className="max-w-2xl space-y-5">
      <div className="space-y-3 rounded-glass border border-line bg-surface/40 p-4">
        <MonoLabel>add a user</MonoLabel>
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex-1">
            <span className="mono-label">email</span>
            <input
              className={`${INPUT} mt-1.5 w-full`}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="teammate@example.com"
            />
          </label>
          <label className="flex-1">
            <span className="mono-label">name (optional)</span>
            <input
              className={`${INPUT} mt-1.5 w-full`}
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Full name"
            />
          </label>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex-1">
            <span className="mono-label">password (min 8)</span>
            <input
              className={`${INPUT} mt-1.5 w-full`}
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="set a password they can sign in with"
            />
          </label>
          <select
            className={INPUT}
            value={role}
            onChange={(e) => setRole(e.target.value as UserRole)}
            aria-label="role for the new user"
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="primary" onClick={() => void create()} disabled={!canCreate}>
            {busy ? 'Working' : 'Create user'}
          </Button>
          <button
            type="button"
            onClick={() => void invite()}
            disabled={!email.trim() || busy}
            className="mono-label text-muted hover:text-accent disabled:opacity-50"
          >
            invite by email instead
          </button>
        </div>
      </div>
      {error ? <p className="text-sm text-danger">{error}</p> : null}
      {notice ? <p className="text-sm text-accent">{notice}</p> : null}

      <ul className="divide-y divide-line/60">
        {users.map((user) => (
          <li key={user.id} className="flex flex-wrap items-center gap-3 py-3">
            <span
              aria-hidden
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent/20 font-mono text-sm text-accent"
            >
              {(user.name?.trim() || user.email).charAt(0).toUpperCase()}
            </span>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm text-cream">{user.name?.trim() || user.email}</div>
              <div className="truncate text-xs text-muted">{user.email}</div>
            </div>
            {user.status === 'invited' ? <Pill variant="grey">invited</Pill> : null}
            <select
              className={INPUT}
              value={user.role}
              onChange={(e) => void changeRole(user.id, e.target.value as UserRole)}
              aria-label={`role for ${user.email}`}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => void setUserPassword(user.id, user.name?.trim() || user.email)}
              className="mono-label rounded-md border border-line px-2 py-1 text-muted hover:border-accent hover:text-accent"
            >
              set password
            </button>
            <button
              type="button"
              onClick={() => void remove(user.id)}
              className="mono-label rounded-md border border-line px-2 py-1 text-muted hover:border-danger hover:text-danger"
            >
              remove
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

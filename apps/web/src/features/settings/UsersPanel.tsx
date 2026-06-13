import { useCallback, useEffect, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { api } from '../../app/client';
import { Button, MonoLabel, Pill } from '../../components/primitives';

type UserRead = Schemas['UserRead'];
type UserRole = Schemas['UserInvite']['role'];

const ROLES: UserRole[] = ['owner', 'admin', 'member'];
const INPUT =
  'rounded-md border border-line bg-canvas px-3 py-2 text-sm text-cream outline-none focus:border-accent';

// Users: list everyone with access, invite by email, change a role, and remove (soft delete),
// over the /users endpoints.
export function UsersPanel() {
  const [users, setUsers] = useState<UserRead[] | null>(null);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<UserRole>('member');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const { data } = await api.GET('/users');
    setUsers((data as UserRead[]) ?? []);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const invite = async () => {
    const value = email.trim();
    if (!value || busy) return;
    setBusy(true);
    setError(null);
    const { error: err } = await api.POST('/users/invite', {
      body: { email: value, role },
    });
    if (err) {
      setError('Could not invite that email. It may already exist.');
    } else {
      setEmail('');
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

  const remove = async (id: number) => {
    await api.DELETE('/users/{user_id}', { params: { path: { user_id: id } } });
    await load();
  };

  if (!users) return <MonoLabel tone="faint">loading users</MonoLabel>;

  return (
    <div className="max-w-2xl space-y-5">
      <div className="flex flex-wrap items-end gap-2 rounded-glass border border-line bg-surface/40 p-4">
        <label className="flex-1">
          <span className="mono-label">invite by email</span>
          <input
            className={`${INPUT} mt-1.5 w-full`}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="teammate@example.com"
          />
        </label>
        <select
          className={INPUT}
          value={role}
          onChange={(e) => setRole(e.target.value as UserRole)}
          aria-label="role for the invite"
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        <Button variant="primary" onClick={() => void invite()} disabled={!email.trim() || busy}>
          {busy ? 'Inviting' : 'Invite'}
        </Button>
      </div>
      {error ? <p className="text-sm text-danger">{error}</p> : null}

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

import { useEffect, useState } from 'react';
import type { Schemas } from '@nexaosweb/api-client';

import { useAuth } from '../../app/AuthProvider';
import { api } from '../../app/client';
import { Button, MonoLabel } from '../../components/primitives';

type General = Schemas['GeneralSettings'];

const INPUT =
  'w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-cream outline-none focus:border-accent';

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mono-label">{label}</span>
      {hint ? <span className="mt-0.5 block text-xs text-muted">{hint}</span> : null}
      <div className="mt-1.5">{children}</div>
    </label>
  );
}

// General: the signed in profile plus the workspace defaults (the system level instruction,
// timezone, appearance, language, notifications), persisted through /auth/me and
// /settings/general.
export function GeneralPanel() {
  const { me, refresh } = useAuth();
  const [name, setName] = useState('');
  const [general, setGeneral] = useState<General | null>(null);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);

  useEffect(() => {
    setName(me?.name ?? '');
  }, [me?.name]);

  useEffect(() => {
    api
      .GET('/settings/general')
      .then(({ data }) => {
        if (data) setGeneral(data as General);
      })
      .catch(() => setStatus({ kind: 'error', text: 'Could not load general settings.' }));
  }, []);

  const patch = (changes: Partial<General>) =>
    setGeneral((prev) => (prev ? { ...prev, ...changes } : prev));

  const save = async () => {
    if (!general) return;
    setSaving(true);
    setStatus(null);
    try {
      if ((me?.name ?? '') !== name) {
        const { error } = await api.PATCH('/auth/me', { body: { name } });
        if (error) throw new Error('profile');
        await refresh();
      }
      // appearance is a plain string here but the patch type narrows to a union; the values
      // come from the fixed select, so the assertion is safe.
      const { error } = await api.PATCH('/settings/general', {
        body: general as Schemas['GeneralSettingsPatch'],
      });
      if (error) throw new Error('general');
      setStatus({ kind: 'ok', text: 'Saved.' });
    } catch {
      setStatus({ kind: 'error', text: 'Could not save. Check the Brain connection.' });
    } finally {
      setSaving(false);
    }
  };

  if (!general) return <MonoLabel tone="faint">loading general settings</MonoLabel>;

  return (
    <div className="max-w-2xl space-y-6">
      <section className="space-y-4">
        <MonoLabel tone="accent">profile</MonoLabel>
        <Field label="display name">
          <input className={INPUT} value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="email" hint="Your sign in identity, managed in Users.">
          <input className={`${INPUT} opacity-60`} value={me?.email ?? ''} readOnly />
        </Field>
      </section>

      <section className="space-y-4 border-t border-line pt-6">
        <MonoLabel tone="accent">workspace</MonoLabel>
        <Field
          label="general model instructions"
          hint="The system level instruction prepended to model work across the app."
        >
          <textarea
            className={INPUT}
            rows={4}
            value={general.general_instructions}
            onChange={(e) => patch({ general_instructions: e.target.value })}
            placeholder="For example: answer concisely, US English, no jargon."
          />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="timezone">
            <input
              className={INPUT}
              value={general.timezone}
              onChange={(e) => patch({ timezone: e.target.value })}
            />
          </Field>
          <Field label="language">
            <input
              className={INPUT}
              value={general.language}
              onChange={(e) => patch({ language: e.target.value })}
            />
          </Field>
          <Field label="appearance">
            <select
              className={INPUT}
              value={general.appearance}
              onChange={(e) => patch({ appearance: e.target.value })}
            >
              <option value="system">System</option>
              <option value="dark">Dark</option>
              <option value="light">Light</option>
            </select>
          </Field>
          <Field label="notifications">
            <button
              type="button"
              role="switch"
              aria-checked={general.notifications}
              aria-label="notifications"
              onClick={() => patch({ notifications: !general.notifications })}
              className={[
                'relative h-6 w-11 rounded-full border transition',
                general.notifications ? 'border-accent bg-accent' : 'border-line bg-white/5',
              ].join(' ')}
            >
              <span
                className={[
                  'absolute top-0.5 h-4 w-4 rounded-full bg-cream transition-all',
                  general.notifications ? 'left-[22px]' : 'left-0.5',
                ].join(' ')}
              />
            </button>
          </Field>
        </div>
      </section>

      <div className="flex items-center gap-3 border-t border-line pt-4">
        <Button variant="primary" onClick={() => void save()} disabled={saving}>
          {saving ? 'Saving' : 'Save changes'}
        </Button>
        {status ? (
          <span className={`text-sm ${status.kind === 'ok' ? 'text-status-green' : 'text-danger'}`}>
            {status.text}
          </span>
        ) : null}
      </div>
    </div>
  );
}

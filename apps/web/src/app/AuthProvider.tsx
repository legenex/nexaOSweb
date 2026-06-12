// Auth layer. On mount it asks the Brain who the caller is. The browser uses the session
// cookie, the desktop wrapper authenticates with its bearer. Exposes login and logout.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import { apiJson } from './api';

export interface Me {
  authenticated: boolean;
  kind: string;
  user_id: number | null;
  email: string | null;
}

interface AuthState {
  status: 'loading' | 'authenticated' | 'anonymous';
  me: Me | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthState['status']>('loading');
  const [me, setMe] = useState<Me | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await apiJson<Me>('/auth/me');
      setMe(data);
      setStatus(data.authenticated ? 'authenticated' : 'anonymous');
    } catch {
      setMe(null);
      setStatus('anonymous');
    }
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      await apiJson('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });
      await refresh();
    },
    [refresh],
  );

  const logout = useCallback(async () => {
    await apiJson('/auth/logout', { method: 'POST' });
    setMe(null);
    setStatus('anonymous');
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = useMemo<AuthState>(
    () => ({ status, me, login, logout, refresh }),
    [status, me, login, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (context === null) throw new Error('useAuth must be used within AuthProvider');
  return context;
}

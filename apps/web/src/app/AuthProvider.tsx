// Auth layer. On mount it asks the Brain who the caller is. The browser uses the session
// cookie, the desktop wrapper authenticates with its bearer. Exposes login and logout.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import { api } from './client';

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
    const { data, error } = await api.GET('/auth/me');
    if (error || !data) {
      setMe(null);
      setStatus('anonymous');
      return;
    }
    setMe(data as Me);
    setStatus(data.authenticated ? 'authenticated' : 'anonymous');
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const { error } = await api.POST('/auth/login', { body: { email, password } });
      if (error) throw new Error('login failed');
      await refresh();
    },
    [refresh],
  );

  const logout = useCallback(async () => {
    await api.POST('/auth/logout');
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

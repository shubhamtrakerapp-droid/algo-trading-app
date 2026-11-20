import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { api, setAuthToken, getAuthToken } from '../services/api';
import { supabase } from '../services/supabase';

export interface AuthUser {
  id: number;
  email: string;
  username: string;
  role: string;
}

export interface AuthContextType {
  user: AuthUser | null;
  sessionToken: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, username?: string) => Promise<void>;
  logout: () => Promise<void>;
  forgotPassword: (email: string) => Promise<string | undefined>;
  resetPassword: (email: string, token: string, newPassword: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [sessionToken, setSessionToken] = useState<string | null>(() => getAuthToken());
  const [loading, setLoading] = useState<boolean>(true);

  // Restore session on initial mount
  useEffect(() => {
    let isMounted = true;

    async function initSession() {
      const storedToken = getAuthToken();
      if (!storedToken) {
        if (isMounted) setLoading(false);
        return;
      }

      try {
        const response = await api.authGetMe();
        if (isMounted && response?.user) {
          setUser(response.user);
          setSessionToken(storedToken);
        }
      } catch (err) {
        console.warn('Failed to restore session or session expired:', err);
        setAuthToken(null);
        if (isMounted) {
          setUser(null);
          setSessionToken(null);
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    initSession();

    // Setup Supabase auth listener if available
    let authListener: { subscription?: { unsubscribe: () => void } } | null = null;
    if (supabase) {
      const { data } = supabase.auth.onAuthStateChange(async (event, session) => {
        if (event === 'SIGNED_IN' && session?.access_token) {
          setAuthToken(session.access_token);
          setSessionToken(session.access_token);
          try {
            const me = await api.authGetMe();
            if (isMounted && me?.user) setUser(me.user);
          } catch {
            // ignore
          }
        } else if (event === 'SIGNED_OUT') {
          setAuthToken(null);
          if (isMounted) {
            setSessionToken(null);
            setUser(null);
          }
        } else if (event === 'TOKEN_REFRESHED' && session?.access_token) {
          setAuthToken(session.access_token);
          if (isMounted) setSessionToken(session.access_token);
        }
      });
      authListener = data;
    }

    return () => {
      isMounted = false;
      if (authListener?.subscription) {
        authListener.subscription.unsubscribe();
      }
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    // 1. Backend Login with Allowlist Enforcement & Rate Limiting
    const data = await api.authLogin({ email, password });
    if (!data.access_token) {
      throw new Error('Authentication failed: No access token received.');
    }

    // 2. Also authenticate Supabase Auth session if configured
    if (supabase) {
      try {
        await supabase.auth.signInWithPassword({ email, password });
      } catch {
        // Supabase sync failure non-blocking for local backend
      }
    }

    setAuthToken(data.access_token);
    setSessionToken(data.access_token);
    setUser(data.user);
  }, []);

  const signup = useCallback(async (email: string, password: string, username?: string) => {
    // 1. Backend Signup with Allowlist Check
    const data = await api.authSignup({ email, password, username });
    if (!data.access_token) {
      throw new Error('Registration failed: No access token received.');
    }

    // 2. Supabase Auth signup if available
    if (supabase) {
      try {
        await supabase.auth.signUp({ email, password });
      } catch {
        // non-blocking
      }
    }

    setAuthToken(data.access_token);
    setSessionToken(data.access_token);
    setUser(data.user);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.authLogout();
    } catch {
      // ignore
    }

    if (supabase) {
      try {
        await supabase.auth.signOut();
      } catch {
        // ignore
      }
    }

    setAuthToken(null);
    setSessionToken(null);
    setUser(null);
  }, []);

  const forgotPassword = useCallback(async (email: string) => {
    if (supabase) {
      try {
        await supabase.auth.resetPasswordForEmail(email, {
          redirectTo: `${window.location.origin}/reset-password`,
        });
      } catch {
        // fallback to backend
      }
    }
    const res = await api.authForgotPassword({ email });
    return res.reset_token;
  }, []);

  const resetPassword = useCallback(async (email: string, token: string, newPassword: string) => {
    await api.authResetPassword({
      email,
      reset_token: token,
      new_password: newPassword,
    });
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        sessionToken,
        loading,
        login,
        signup,
        logout,
        forgotPassword,
        resetPassword,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

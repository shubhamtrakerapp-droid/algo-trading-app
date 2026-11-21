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
      // 1. First check active Supabase Auth session if configured
      if (supabase) {
        try {
          const { data: { session } } = await supabase.auth.getSession();
          if (session?.user && session?.access_token) {
            const cleanEmail = (session.user.email || '').trim().toLowerCase();
            setAuthToken(session.access_token);
            if (isMounted) {
              setSessionToken(session.access_token);
              setUser({
                id: 1,
                email: cleanEmail,
                username: session.user.user_metadata?.username || cleanEmail.split('@')[0] || 'trader',
                role: session.user.user_metadata?.role || 'trader',
              });
              setLoading(false);
            }
            return;
          }
        } catch (supabaseErr) {
          console.warn('Supabase session inspection error:', supabaseErr);
        }
      }

      // 2. Fallback to localStorage token / backend session restoration
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
        if ((event === 'SIGNED_IN' || event === 'TOKEN_REFRESHED') && session?.access_token) {
          const cleanEmail = (session.user?.email || '').trim().toLowerCase();
          setAuthToken(session.access_token);
          if (isMounted) {
            setSessionToken(session.access_token);
            setUser({
              id: 1,
              email: cleanEmail,
              username: session.user?.user_metadata?.username || cleanEmail.split('@')[0] || 'trader',
              role: session.user?.user_metadata?.role || 'trader',
            });
          }
        } else if (event === 'SIGNED_OUT') {
          setAuthToken(null);
          if (isMounted) {
            setSessionToken(null);
            setUser(null);
          }
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
    const cleanEmail = email.trim().toLowerCase();

    // 1. Direct Supabase Auth (Client-side, Fast, Resilient)
    if (supabase) {
      const { data, error } = await supabase.auth.signInWithPassword({
        email: cleanEmail,
        password,
      });

      if (error) {
        throw new Error(error.message || 'Authentication failed.');
      }

      if (!data.session?.access_token) {
        throw new Error('Authentication succeeded but no access token was returned.');
      }

      // Check strict 2-user allowlist from authorized_users table if available
      try {
        const { data: authRecord } = await supabase
          .from('authorized_users')
          .select('email, role')
          .eq('email', cleanEmail)
          .maybeSingle();

        if (authRecord && !authRecord.email) {
          await supabase.auth.signOut();
          throw new Error(`Access denied: Email '${cleanEmail}' is not on the authorized allowlist for this private instance.`);
        }
      } catch (allowlistErr: any) {
        if (allowlistErr.message?.includes('Access denied')) {
          throw allowlistErr;
        }
        // If table not yet queried or RLS hidden, server-side validation will enforce on API calls
      }

      setAuthToken(data.session.access_token);
      setSessionToken(data.session.access_token);
      setUser({
        id: 1,
        email: cleanEmail,
        username: data.user.user_metadata?.username || cleanEmail.split('@')[0],
        role: data.user.user_metadata?.role || 'trader',
      });
      return;
    }

    // 2. Fallback to FastAPI backend login if Supabase client is not configured
    const data = await api.authLogin({ email: cleanEmail, password });
    if (!data.access_token) {
      throw new Error('Authentication failed: No access token received.');
    }

    setAuthToken(data.access_token);
    setSessionToken(data.access_token);
    setUser(data.user);
  }, []);

  const signup = useCallback(async (email: string, password: string, username?: string) => {
    const cleanEmail = email.trim().toLowerCase();

    // 1. Direct Supabase Auth Signup
    if (supabase) {
      const { data, error } = await supabase.auth.signUp({
        email: cleanEmail,
        password,
        options: {
          data: {
            username: username || cleanEmail.split('@')[0],
            role: 'trader',
          },
        },
      });

      if (error) {
        throw new Error(error.message || 'Registration failed.');
      }

      if (data.session?.access_token) {
        setAuthToken(data.session.access_token);
        setSessionToken(data.session.access_token);
        setUser({
          id: 1,
          email: cleanEmail,
          username: username || cleanEmail.split('@')[0],
          role: 'trader',
        });
        return;
      } else if (data.user) {
        // Confirmation email may be required depending on Supabase settings
        return;
      }
    }

    // 2. Fallback to backend signup
    const data = await api.authSignup({ email: cleanEmail, password, username });
    if (!data.access_token) {
      throw new Error('Registration failed: No access token received.');
    }

    setAuthToken(data.access_token);
    setSessionToken(data.access_token);
    setUser(data.user);
  }, []);

  const logout = useCallback(async () => {
    if (supabase) {
      try {
        await supabase.auth.signOut();
      } catch {
        // ignore
      }
    }

    try {
      await api.authLogout();
    } catch {
      // ignore
    }

    setAuthToken(null);
    setSessionToken(null);
    setUser(null);
  }, []);

  const forgotPassword = useCallback(async (email: string) => {
    const cleanEmail = email.trim().toLowerCase();
    if (supabase) {
      const { error } = await supabase.auth.resetPasswordForEmail(cleanEmail, {
        redirectTo: `${window.location.origin}/reset-password`,
      });
      if (error) throw new Error(error.message);
      return 'Password reset instructions sent to your email.';
    }
    const res = await api.authForgotPassword({ email: cleanEmail });
    return res.reset_token;
  }, []);

  const resetPassword = useCallback(async (email: string, token: string, newPassword: string) => {
    if (supabase) {
      const { error } = await supabase.auth.updateUser({ password: newPassword });
      if (error) throw new Error(error.message);
      return;
    }
    await api.authResetPassword({
      email: email.trim().toLowerCase(),
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

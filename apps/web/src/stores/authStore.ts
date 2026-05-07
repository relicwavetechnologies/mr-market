import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { configureApiAuth } from '@/services/apiClient';
import * as usersApi from '@/services/usersApi';
import { useChatStore } from '@/stores/chatStore';
import type { User } from '@/types';

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  showAuthModal: boolean;
  authError: string | null;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, displayName: string) => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  logout: () => void;
  setShowAuthModal: (show: boolean) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      showAuthModal: false,
      authError: null,

      login: async (email: string, password: string) => {
        try {
          const session = await usersApi.login(email.trim(), password);
          set({
            user: session.user,
            accessToken: session.accessToken,
            refreshToken: session.refreshToken,
            isAuthenticated: true,
            showAuthModal: false,
            authError: null,
          });
          await useChatStore.getState().hydrateFromServer();
        } catch (err) {
          const message = (err as Error).message || 'Login failed';
          set({ authError: message });
          throw err;
        }
      },

      signup: async (email: string, password: string, displayName: string) => {
        try {
          const session = await usersApi.signup(email.trim(), password, displayName.trim());
          set({
            user: session.user,
            accessToken: session.accessToken,
            refreshToken: session.refreshToken,
            isAuthenticated: true,
            showAuthModal: false,
            authError: null,
          });
          await useChatStore.getState().hydrateFromServer();
        } catch (err) {
          const message = (err as Error).message || 'Signup failed';
          set({ authError: message });
          throw err;
        }
      },

      loginWithGoogle: async () => {
        throw new Error('Google sign-in is coming soon');
      },

      logout: () => {
        void usersApi.logout().catch(() => undefined);
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          authError: null,
        });
        useChatStore.getState().clearAll();
      },

      setShowAuthModal: (show: boolean) => {
        set({ showAuthModal: show, authError: null });
      },
    }),
    {
      name: 'midas-auth',
      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated,
      }),
    },
  ),
);

configureApiAuth({
  getAccessToken: () => useAuthStore.getState().accessToken,
  refreshAccessToken: async () => {
    const refreshToken = useAuthStore.getState().refreshToken;
    if (!refreshToken) return null;
    try {
      const accessToken = await usersApi.refresh(refreshToken);
      useAuthStore.setState({ accessToken, isAuthenticated: true });
      return accessToken;
    } catch {
      useAuthStore.getState().logout();
      return null;
    }
  },
  onUnauthorized: () => {
    useAuthStore.getState().logout();
  },
});

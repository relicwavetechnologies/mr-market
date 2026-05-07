import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { User } from "@/types";

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  showAuthModal: boolean;

  login: (email: string, _password: string) => Promise<void>;
  logout: () => void;
  setShowAuthModal: (show: boolean) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      showAuthModal: false,

      login: async (email: string, _password: string) => {
        // Mock login -- replace with real API call
        const mockUser: User = {
          id: crypto.randomUUID(),
          email,
          name: email.split("@")[0],
          riskProfile: "moderate",
        };
        set({ user: mockUser, isAuthenticated: true, showAuthModal: false });
      },

      logout: () => {
        set({ user: null, isAuthenticated: false });
      },

      setShowAuthModal: (show: boolean) => {
        set({ showAuthModal: show });
      },
    }),
    {
      name: "mr-market-auth",
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    },
  ),
);

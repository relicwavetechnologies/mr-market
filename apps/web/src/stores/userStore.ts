import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { RiskProfile } from "@/types";

interface UserState {
  riskProfile: RiskProfile | null;
  isOnboarded: boolean;
  setProfile: (profile: RiskProfile) => void;
  resetProfile: () => void;
}

export const useUserStore = create<UserState>()(
  persist(
    (set) => ({
      riskProfile: null,
      isOnboarded: false,

      setProfile: (profile) =>
        set({ riskProfile: profile, isOnboarded: true }),

      resetProfile: () =>
        set({ riskProfile: null, isOnboarded: false }),
    }),
    {
      name: "mr-market-user",
    },
  ),
);

import type { ReactNode } from "react";
import { Sidebar } from "./Sidebar";
import { AuthModal } from "@/components/auth/AuthModal";
import { useAuthStore } from "@/stores/authStore";

interface AppLayoutProps {
  children: ReactNode;
}

export function AppLayout({ children }: AppLayoutProps) {
  const showAuthModal = useAuthStore((s) => s.showAuthModal);

  return (
    <div className="flex h-screen overflow-hidden bg-bg-primary">
      <Sidebar />
      <main className="flex flex-1 flex-col overflow-hidden">{children}</main>
      {showAuthModal && <AuthModal />}
    </div>
  );
}

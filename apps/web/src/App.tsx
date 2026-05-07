import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ChatPage } from "@/pages/ChatPage";
import { OnboardingPage } from "@/pages/OnboardingPage";
import { useUserStore } from "@/stores/userStore";

export function App() {
  const isOnboarded = useUserStore((s) => s.isOnboarded);

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/"
          element={isOnboarded ? <ChatPage /> : <Navigate to="/onboarding" replace />}
        />
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

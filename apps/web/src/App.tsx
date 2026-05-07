import { useEffect } from 'react';
import { Routes, Route } from 'react-router-dom';
import { AppLayout } from '@/components/layout/AppLayout';
import { HomePage } from '@/pages/HomePage';
import { ChatPage } from '@/pages/ChatPage';
import { useAuthStore } from '@/stores/authStore';
import { useChatStore } from '@/stores/chatStore';

export default function App() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const hydrateFromServer = useChatStore((s) => s.hydrateFromServer);

  useEffect(() => {
    if (isAuthenticated) void hydrateFromServer().catch(() => undefined);
  }, [isAuthenticated, hydrateFromServer]);

  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/chat/:id" element={<ChatPage />} />
      </Routes>
    </AppLayout>
  );
}

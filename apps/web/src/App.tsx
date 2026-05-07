import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ChatPage } from "@/pages/ChatPage";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

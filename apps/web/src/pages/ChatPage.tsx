import { ChatContainer } from "@/components/chat/ChatContainer";
import { AuthBanner } from "@/components/common/AuthBanner";
import { Disclaimer } from "@/components/common/Disclaimer";
import { TrendingUp } from "lucide-react";

export function ChatPage() {
  return (
    <div className="flex h-screen flex-col bg-gray-950">
      {/* Header */}
      <header className="flex items-center gap-3 border-b border-gray-800 px-6 py-3">
        <TrendingUp className="h-6 w-6 text-emerald-400" />
        <h1 className="text-lg font-semibold text-white">Mr. Market</h1>
        <span className="rounded-full bg-emerald-900/50 px-2 py-0.5 text-xs text-emerald-300">
          AI Assistant
        </span>
      </header>

      {/* Auth status banner */}
      <div className="border-b border-gray-800 px-6 py-2">
        <AuthBanner />
      </div>

      {/* Main chat area */}
      <main className="flex min-h-0 flex-1">
        <div className="flex flex-1 flex-col">
          <ChatContainer />
        </div>
      </main>

      {/* Footer disclaimer */}
      <Disclaimer />
    </div>
  );
}

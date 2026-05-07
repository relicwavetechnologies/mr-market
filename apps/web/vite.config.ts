import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_PROXY_TARGET || "http://localhost:8000";

  // Note: `/chat` is also a SPA route (`/chat/:id`). Use a regex that matches
  // ONLY the exact `/chat` path so hard reloads of `/chat/<uuid>` fall through
  // to Vite's index.html instead of being proxied to the backend (which would
  // 404 — backend only exposes POST /chat, not GET /chat/<id>).
  const proxy = {
    "^/chat$": { target: apiTarget, changeOrigin: true },
    "/api": { target: apiTarget, changeOrigin: true, ws: true },
    "/healthz": { target: apiTarget, changeOrigin: true },
    "/quote": { target: apiTarget, changeOrigin: true },
    "/news": { target: apiTarget, changeOrigin: true },
    "/technicals": { target: apiTarget, changeOrigin: true },
    "/levels": { target: apiTarget, changeOrigin: true },
    "/holding": { target: apiTarget, changeOrigin: true },
    "/admin": { target: apiTarget, changeOrigin: true },
  };

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { "@": path.resolve(__dirname, "./src") },
    },
    server: {
      host: "0.0.0.0",
      port: 5173,
      strictPort: true,
      proxy,
    },
  };
});

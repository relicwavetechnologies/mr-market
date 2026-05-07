import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_PROXY_TARGET || "http://localhost:8000";

  const proxy = Object.fromEntries(
    ["/api", "/healthz", "/chat", "/quote", "/news", "/admin"].map((p) => [
      p,
      { target: apiTarget, changeOrigin: true, ws: p === "/api" },
    ]),
  );

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

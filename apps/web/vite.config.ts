import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5174,
    strictPort: true,
    host: "0.0.0.0",
    proxy: {
      "/api": { target: "http://localhost:8001", changeOrigin: true, ws: true },
      "/healthz": { target: "http://localhost:8001", changeOrigin: true },
      "/chat": { target: "http://localhost:8001", changeOrigin: true },
      "/quote": { target: "http://localhost:8001", changeOrigin: true },
      "/news": { target: "http://localhost:8001", changeOrigin: true },
      "/admin": { target: "http://localhost:8001", changeOrigin: true },
    },
  },
});

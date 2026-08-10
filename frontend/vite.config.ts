/// <reference types="vitest/config" />

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const BACKEND = "http://127.0.0.1:8765";
const BACKEND_WS = "ws://127.0.0.1:8765";

export default defineConfig(({ command }) => ({
  plugins: [react()],
  define: {
    // Vite 8's ws proxy aborts the upgrade write on this setup, so the socket
    // connects straight to the backend in dev. A production build is served
    // from the backend itself and stays same-origin.
    "import.meta.env.VITE_WS_URL": JSON.stringify(
      command === "serve" ? `${BACKEND_WS}/ws/captions` : "",
    ),
  },
  server: {
    // 5173 is taken by other local tooling on this machine; a fixed port keeps
    // the dev URL predictable instead of silently sliding to 5174.
    port: 5180,
    strictPort: true,
    // HTTP still goes through the proxy so the UI stays same-origin for the
    // control API.
    proxy: {
      "/api": { target: BACKEND, changeOrigin: false },
    },
  },
  test: {
    environment: "jsdom",
    pool: "threads",
    // Each jsdom worker is expensive on this machine; unbounded parallelism
    // makes workers time out before they finish booting.
    maxWorkers: 2,
    setupFiles: "./src/test/setup.ts",
  },
}));

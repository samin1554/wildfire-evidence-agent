/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The browser only ever talks to our own Go API (proxied here); no provider calls, no secrets, no VITE_ secrets.
const api = process.env.API_PROXY_TARGET ?? "http://localhost:8080";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // MapLibre v6 loads its Web Worker via new URL(..., import.meta.url); pre-bundling breaks that URL
  optimizeDeps: { exclude: ["maplibre-gl"] },
  server: {
    host: true,
    port: 5173,
    proxy: { "/v1": { target: api, changeOrigin: true }, "/health": { target: api, changeOrigin: true } },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});

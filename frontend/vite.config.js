import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Frontend, API and WS are all served from the same origin in production.
// During local dev, proxy /api and /ws to the backend on port 7860.
export default defineConfig({
  base: "/",
  plugins: [react()],
  build: {
    outDir: "dist",
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:7860",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://localhost:7860",
        ws: true,
      },
      "/napcat": {
        target: "http://localhost:7860",
        changeOrigin: true,
        ws: true,
      },
    },
  },
});

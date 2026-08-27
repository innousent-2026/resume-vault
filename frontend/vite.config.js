import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API runs on 5057; proxying keeps the dashboard same-origin in dev.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET || "http://127.0.0.1:5057",
        changeOrigin: true,
      },
    },
  },
});

import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    port: 3000,
    // Local Vite uses localhost. The Compose build uses nginx.conf instead.
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true } },
  },
});

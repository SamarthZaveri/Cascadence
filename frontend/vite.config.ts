import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    port: 3000,
    // In Docker Compose, the frontend container proxies API calls to the backend
    // service by name (see infra/docker-compose.yml). Locally without Docker, set
    // VITE_API_URL in frontend/.env instead.
    proxy: {
      '/api': { target: 'http://backend:8000', changeOrigin: true },
    },
  },
})

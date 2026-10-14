import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Запросы /api/* проксируются в backend, чтобы не возиться с CORS в разработке.
const apiTarget = process.env.API_PROXY_TARGET ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: apiTarget, rewrite: (path) => path.replace(/^\/api/, '') },
    },
  },
})

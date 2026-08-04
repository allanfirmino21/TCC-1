import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxy /api → FastAPI (porta 8000): evita CORS e permite usar caminhos
// relativos no código do frontend.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})

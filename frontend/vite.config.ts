import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/session': 'http://localhost:8000',
      '/pipeline': 'http://localhost:8000',
      '/chat': 'http://localhost:8000',
      '/plan': 'http://localhost:8000',
      '/privacy': 'http://localhost:8000',
    },
  },
})

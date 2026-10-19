import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendProxy = {
  target: process.env.F1HUB_PREVIEW_API || 'http://127.0.0.1:8000',
  changeOrigin: true,
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react({
      babel: {
        plugins: [['babel-plugin-react-compiler']],
      },
    }),
  ],
  server: {
    host: true,
    port: 5173,
    allowedHosts: true,
    watch: {
      ignored: ['**/public/race-game/**'],
    },
    proxy: {
      '/api': backendProxy,
      '/static': backendProxy,
      '/assets': backendProxy,
    }
  },
  // Built JS/CSS live in /static; preview must serve these from dist itself.
  preview: {
    proxy: { '/api': backendProxy, '/assets': backendProxy },
  },
  build: {
    assetsDir: 'static',
    manifest: true,
  }
})

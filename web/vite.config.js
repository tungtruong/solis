import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
const apiProxyTarget = process.env.SOLIS_DEV_API_PROXY_TARGET || 'https://wssmeas-mvp-202603152044.web.app'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
})

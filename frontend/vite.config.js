import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 15002,
    proxy: {
      '/v1': {
        target: 'http://127.0.0.1:15001',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://127.0.0.1:15001',
        changeOrigin: true,
      },
    },
  },
})

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: '/darwen/',
  server: {
    host: '0.0.0.0',
    port: 15002,
    allowedHosts: ['dev-cn-01.yios.cn'],
    proxy: {
      '/darwen/v1': {
        target: 'http://127.0.0.1:15003',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/darwen/, ''),
      },
      '/darwen/v2': {
        target: 'http://127.0.0.1:15003',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/darwen/, ''),
      },
    },
  },
})

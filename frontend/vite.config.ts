import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: '../static/dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      // 127.0.0.1 explicitly: Node resolves `localhost` to ::1 first and
      // the API server only listens on IPv4.
      '/api': 'http://127.0.0.1:8090',
      '/events': {
        target: 'http://127.0.0.1:8090',
        // SSE is plain HTTP; proxy must not buffer the stream.
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            proxyRes.headers['cache-control'] = 'no-cache'
          })
        },
      },
    },
  },
})

import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backend = env.VITE_BACKEND_PROXY || 'http://127.0.0.1:8000'
  return {
    plugins: [
      vue(),
      AutoImport({ resolvers: [ElementPlusResolver()] }),
      Components({ resolvers: [ElementPlusResolver()] }),
    ],
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    server: {
      port: 5173,
      proxy: {
        '/api': { target: backend, changeOrigin: true },
        '/healthz': { target: backend, changeOrigin: true },
        '/readyz': { target: backend, changeOrigin: true },
        '/metrics': { target: backend, changeOrigin: true },
      },
    },
    build: {
      target: 'es2020',
      sourcemap: mode !== 'production',
      chunkSizeWarningLimit: 1024,
      rollupOptions: {
        output: {
          manualChunks: {
            vendor: ['vue', 'vue-router', 'pinia'],
            element: ['element-plus'],
            echarts: ['echarts', 'vue-echarts'],
          },
        },
      },
    },
  }
})

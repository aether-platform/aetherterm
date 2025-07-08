import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  base: './', // Set the base public path for assets
  plugins: [
    vue(),
    vueDevTools(),
  ],
  define: {
    global: 'globalThis',
    process: {
      env: {}
    }
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      'stream': 'stream-browserify',
      'buffer': 'buffer',
      'util': 'util'
    },
  },
  build: {
    rollupOptions: {
      output: {
        entryFileNames: `assets/[name].[hash].js`,
        chunkFileNames: `assets/[name].[hash].js`,
        assetFileNames: `assets/[name].[hash].[ext]`,
        manualChunks: {
          'vue-vendor': ['vue', 'vue-router', 'pinia'],
          'vuetify': ['vuetify'],
          'terminal': ['@xterm/xterm', 'xterm'],
          'socket': ['socket.io-client'],
          'vega': ['vega', 'vega-lite', 'vega-embed']
        }
      }
    },
    target: 'esnext',
    minify: 'esbuild',
    sourcemap: false
  },
  server: {
    watch: {
      usePolling: true
    },
    proxy: {
      '/api': {
        target: 'http://localhost:57575',
        changeOrigin: true,
        secure: false
      },
      '/socket.io': {
        target: 'http://localhost:57575',
        changeOrigin: true,
        ws: true
      }
    }
  },
  optimizeDeps: {
    include: ['vue', 'vue-router', 'pinia', 'vuetify', 'socket.io-client', 'util', 'buffer', 'stream-browserify']
  }
})

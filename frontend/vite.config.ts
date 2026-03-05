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
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    rollupOptions: {
      output: {
        entryFileNames: `assets/[name].[hash].js`,
        chunkFileNames: `assets/[name].[hash].js`,
        assetFileNames: `assets/[name].[hash].[ext]`,
        manualChunks(id) {
          if (id.includes('node_modules')) {
            // Vue core ecosystem
            if (id.includes('/vue/') || id.includes('vue-router') || id.includes('pinia')) {
              return 'vendor-vue'
            }
            // xterm terminal emulator
            if (id.includes('@xterm/')) {
              return 'vendor-xterm'
            }
            // Chat libraries (lazy-loaded via routes)
            if (id.includes('deep-chat') || id.includes('vue-advanced-chat')) {
              return 'vendor-chat'
            }
          }
        },
      }
    }
  },
  server: {
    watch: {
      usePolling: true
    }
  }
})

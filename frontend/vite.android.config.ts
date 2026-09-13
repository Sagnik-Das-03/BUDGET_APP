import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Separate build target for the Android app's trimmed dashboard-only page
// (src/AndroidApp.tsx) - same components/aliases/plugins as the desktop
// app's vite.config.ts, but its own HTML entry (android.html) and its own
// output directory, so `npm run build` (desktop) and `npm run build:android`
// never clobber each other's dist folders.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    outDir: 'dist-android',
    rollupOptions: {
      input: path.resolve(__dirname, 'android.html'),
    },
  },
})

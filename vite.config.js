import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: 'frontend',
  envDir: __dirname,
  base: '/static/dist/',
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/webhook': 'http://localhost:8000',
      '/static': 'http://localhost:8000',
    },
  },
  build: {
    outDir: '../app/static/dist',
    emptyOutDir: true,
    rollupOptions: {
      input: resolve(__dirname, 'frontend/index.html'),
      output: {
        entryFileNames: 'mini-app.js',
        chunkFileNames: 'chunks/[name].js',
        assetFileNames: '[name][extname]'
      }
    }
  }
});

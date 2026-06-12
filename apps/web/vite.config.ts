import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// In dev the web app calls /api, proxied to the local Brain on port 8847.
// In production the Plesk Nginx serves the same /api path to the Brain.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8847',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// In dev the web app calls /api, proxied to the local Brain on port 8847.
// In production the Plesk Nginx serves the same /api path to the Brain.
export default defineConfig({
  plugins: [react()],
  server: {
    // host true binds 0.0.0.0 so the Codespaces (and other tunnel) forwarders can reach the
    // dev server. allowedHosts trusts the Codespaces forwarded domain, which carries the
    // codespace name, so a codespace rename does not break the preview link.
    host: true,
    port: 5173,
    allowedHosts: ['.app.github.dev'],
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

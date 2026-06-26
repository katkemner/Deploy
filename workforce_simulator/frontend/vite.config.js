import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The dev server runs on 5173 and talks to the FastAPI backend at
// http://127.0.0.1:8000 (CORS is enabled on the backend). To point at a
// different backend, set VITE_API_BASE before running `npm run dev`.
//
// In GitHub Codespaces the browser tab is served from a forwarded
// *.app.github.dev URL and cannot reach the codespace's own localhost, so
// the frontend is configured (via VITE_API_BASE=/api) to call same-origin
// `/api/*` paths, which Vite proxies to the backend below. This keeps
// everything on a single forwarded port (5173).
export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // bind 0.0.0.0 so Codespaces can forward the port
    port: 5173,
    open: false,
    // Allow the Codespaces forwarded host through Vite's host check.
    allowedHosts: ['.app.github.dev'],
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});

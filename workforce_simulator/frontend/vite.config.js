import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The dev server runs on 5173 and talks to the FastAPI backend at
// http://127.0.0.1:8000 (CORS is enabled on the backend). To point at a
// different backend, set VITE_API_BASE before running `npm run dev`.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    open: false,
  },
});

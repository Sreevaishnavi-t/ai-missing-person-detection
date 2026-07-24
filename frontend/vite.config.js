import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
//
// Design decision — @tailwindcss/vite plugin:
// Tailwind v4 dropped the PostCSS-based setup in favour of a native Vite
// plugin.  The plugin integrates directly into Vite's transform pipeline,
// which means Tailwind CSS is processed at build time alongside JS/JSX —
// no separate PostCSS step, no tailwind.config.js file, and faster HMR.
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),   // Tailwind v4 Vite-native plugin
  ],
  server: {
    // Proxy /api calls to the FastAPI backend so the browser never sees a
    // cross-origin request in development.  We keep CORS middleware on the
    // backend too for production deployments where frontend and backend are
    // on separate domains.
    proxy: {
      '/enroll':      'http://localhost:8000',
      '/watchlist':   'http://localhost:8000',
      '/start':       'http://localhost:8000',
      '/stop':        'http://localhost:8000',
      '/results':     'http://localhost:8000',
      '/stream':      'http://localhost:8000',
      '/screenshots': 'http://localhost:8000',
    },
  },
})

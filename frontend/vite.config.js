import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // `vite preview` serves the built demo behind any host name (reverse proxy / cloud).
  preview: { allowedHosts: true },
})

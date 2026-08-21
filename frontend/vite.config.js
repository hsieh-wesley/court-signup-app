import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  // A production build must never silently ship pointed at localhost --
  // fail the build itself (not just at runtime in the browser) when the
  // real API host hasn't been configured.
  if (mode === 'production' && !env.VITE_API_BASE_URL) {
    throw new Error(
      'VITE_API_BASE_URL is required for a production build and was not set. ' +
        'Set it to the real API host before building (see frontend/.env.example).'
    )
  }

  return {
    plugins: [react()],
    server: {
      port: 5183,
      strictPort: true,
    },
  }
})

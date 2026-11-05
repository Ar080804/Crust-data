import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Port 5173 is fixed (TEAM.md rule 7). fs.allow lets us import ../contract (types + fixtures).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, fs: { allow: ['..'] } },
})

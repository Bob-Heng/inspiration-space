import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // 固定 5173 且被占用时直接报错，避免静默换端口后用户看到旧前端
    port: 5173,
    strictPort: true,
  },
})

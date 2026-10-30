import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: process.env.VITE_API_TARGET ?? "http://127.0.0.1:8001", changeOrigin: true },
    },
  },
  build: {
    chunkSizeWarningLimit: 3000,
    rollupOptions: {
      output: {
        manualChunks: {
          monaco: ["monaco-editor/esm/vs/editor/editor.api", "@monaco-editor/react"],
          antd: ["antd", "@ant-design/icons"],
          charts: ["recharts"],
        },
      },
    },
  },
});

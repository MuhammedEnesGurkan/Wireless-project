import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      port: parseInt(env.VITE_PORT ?? "5173"),
      host: true,
      strictPort: true,
      hmr: {
        protocol: "ws",
        host: "localhost",
        port: parseInt(env.VITE_PORT ?? "5173"),
        clientPort: parseInt(env.VITE_PORT ?? "5173"),
      },
      proxy: {
        "/api": {
          target: env.VITE_API_BASE_URL ?? "http://localhost:8000",
          changeOrigin: true,
        },
      },
    },
    build: {
      sourcemap: true,
      rollupOptions: {
        output: {
          manualChunks: {
            vendor:   ["react", "react-dom"],
            charts:   ["recharts"],
            motion:   ["framer-motion"],
            zustand:  ["zustand"],
          },
        },
      },
    },
  };
});


import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    proxy: {
      "/api": {
        target: "http://192.168.4.220:5000",
        changeOrigin: true,
      },
      "/auth": {
        target: "http://192.168.4.220:5000",
        changeOrigin: true,
      },
    },
  },
});

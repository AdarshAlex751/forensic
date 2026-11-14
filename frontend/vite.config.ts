import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// envDir points at the repo root so VITE_* variables come from the one shared .env.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  envDir: "..",
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000" },
  },
});

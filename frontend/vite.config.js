import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

export default defineConfig({
  plugins: [svelte()],
  server: {
    allowedHosts: [
      "localhost",
      "127.0.0.1",
      "0.0.0.0",
      "10.0.1.158",
      "mini.netlob",
    ],
    proxy: {
      "/api": "http://localhost:8000",
      "/eastereggs": "http://localhost:8000",
    },
  },
});

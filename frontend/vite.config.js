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
      "m4.netlob",
    ],
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        ws: true,
      },
      "/eastereggs": "http://localhost:8000",
    },
  },
});

import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";

function page(name: string): string {
  return fileURLToPath(new URL(name, import.meta.url));
}

export default defineConfig({
  build: {
    target: "es2020",
    outDir: "dist",
    rollupOptions: {
      input: {
        main: page("index.html"),
        about: page("about.html"),
        pricing: page("pricing.html"),
        docs: page("docs.html"),
      },
    },
  },
});

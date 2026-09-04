import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath, URL } from "node:url";
import { defineConfig, type Plugin } from "vite";

function page(name: string): string {
  return fileURLToPath(new URL(name, import.meta.url));
}

/** Static hosts (Netlify, Vercel, GitHub Pages, nginx) resolve a request for
 * /about to about/index.html on their own. Vite's dev and preview servers do
 * not, so without this every clean URL 404s locally even though it would work
 * once deployed. Rewrites extensionless paths to their directory index, and
 * only when that file actually exists. */
function directoryIndexUrls(): Plugin {
  let devRoot = "";
  let previewRoot = "";

  const rewriteTo = (root: string) => (req: { url?: string }, _res: unknown, next: () => void) => {
    const raw = req.url ?? "/";
    const path = raw.split(/[?#]/, 1)[0];
    if (path.endsWith("/") || path.includes(".")) return next();
    if (existsSync(resolve(root, `.${path}`, "index.html"))) {
      req.url = `${path}/index.html${raw.slice(path.length)}`;
    }
    next();
  };

  return {
    name: "munshiji-directory-index-urls",
    configResolved(config) {
      devRoot = config.root;
      previewRoot = resolve(config.root, config.build.outDir);
    },
    configureServer(server) {
      server.middlewares.use(rewriteTo(devRoot));
    },
    configurePreviewServer(server) {
      server.middlewares.use(rewriteTo(previewRoot));
    },
  };
}

/* Every page except the homepage lives in its own folder as index.html, so the
 * build emits dist/about/index.html - which static hosts serve at /about, with
 * no .html in the URL and no host-specific rewrite rules. Adding a page means
 * creating <name>/index.html and listing it here. */
export default defineConfig({
  /* Multi-page, not a SPA. Without this Vite falls back to index.html for any
   * path that isn't an exact file match, so a typo'd URL would silently serve
   * the homepage instead of a 404. */
  appType: "mpa",
  plugins: [directoryIndexUrls()],
  build: {
    target: "es2020",
    outDir: "dist",
    rollupOptions: {
      input: {
        main: page("index.html"),
        about: page("about/index.html"),
        pricing: page("pricing/index.html"),
        docs: page("docs/index.html"),
        features: page("features/index.html"),
        download: page("download/index.html"),
        terms: page("terms/index.html"),
        privacy: page("privacy/index.html"),
      },
    },
  },
});

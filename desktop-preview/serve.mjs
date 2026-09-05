// Zero-dependency static server for dist/ — lets you test the Control
// Center UI in a normal browser tab without Rust, Tauri, or WebView2
// installed. Not used by the Tauri build itself; see README.md.
//
// This serves the page *without* a session token, so it can only show the
// interface: the page probes the engine and, if it finds one, sends you to
// the copy the engine serves (which does have a token and can act). Port
// 5181 rather than 5180 deliberately — 5180 is the engine's own
// (config/default.yaml, ui.control_center.port), and taking it would stop
// the real Control Center from starting.
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(fileURLToPath(import.meta.url), "..", "dist");
const PORT = Number(process.env.PORT) || 5181;

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
};

const server = createServer(async (req, res) => {
  const urlPath = decodeURIComponent((req.url ?? "/").split("?")[0]);
  const relative = urlPath === "/" ? "index.html" : urlPath.replace(/^\/+/, "");
  const filePath = normalize(join(ROOT, relative));

  if (!filePath.startsWith(ROOT)) {
    res.writeHead(403).end("Forbidden");
    return;
  }

  try {
    const info = await stat(filePath);
    const target = info.isDirectory() ? join(filePath, "index.html") : filePath;
    const body = await readFile(target);
    res.writeHead(200, { "Content-Type": MIME[extname(target)] ?? "application/octet-stream" });
    res.end(body);
  } catch {
    res.writeHead(404, { "Content-Type": "text/plain" }).end("Not found");
  }
});

server.listen(PORT, () => {
  console.log(`Munshiji Control Center (interface only) → http://localhost:${PORT}/`);
  console.log("For a Control Center that can act, run: uv run munshiji --no-voice");
});

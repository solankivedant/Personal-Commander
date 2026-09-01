# Munshiji — landing page

The public marketing page. A Vite + TypeScript project, not a framework app —
there's no router or component library here, just typed data modules driving
a handful of DOM-rendering functions (the bento grid, the phase track, the
multilingual command demo, the ambient waveform canvas). It builds to plain
static files, so it deploys anywhere that serves HTML.

```bash
npm install
npm run dev       # http://localhost:5173, hot-reloads on save
npm run build     # type-checks (tsc -b) then outputs static files to dist/
npm run preview   # serves the dist/ build locally, for a final check
```

## Layout

```
index.html       Vite entry point — all page markup
src/main.ts       Wires everything up on load
src/data.ts       Typed content: demo phrases, tool cards, roadmap phases
src/waveform.ts   Canvas waveform animation (Waveform class)
src/demo.ts       Multilingual command-demo cycler (CommandDemo class)
src/bento.ts      Renders the "what it controls" tool grid from data.ts
src/roadmap.ts    Renders the phase-track bar from data.ts
src/style.css     All styling — CSS custom properties for light/dark theming
public/           Static assets copied as-is (favicon, etc.)
```

## Updating content

Change copy directly in `index.html`. Change the tool list, roadmap phases, or
demo phrases in `src/data.ts` — the DOM is rendered from those arrays, so nothing
else needs editing to add or reorder an entry.

## Deploying

`npm run build` produces a fully static `dist/` — point Vercel/Netlify/GitHub
Pages at this directory (build command `npm run build`, publish directory
`dist`) with no server-side requirements.

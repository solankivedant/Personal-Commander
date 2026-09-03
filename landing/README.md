# Munshiji - landing page

The public marketing page. A Vite + TypeScript project, not a framework app -
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

This is a multi-page site - `vite.config.ts` lists each `.html` file as a
build entry, so a new page needs adding there too or `npm run build` won't
emit it:

```
index.html         Homepage - the full product pitch, hero mockup, bento grid
about.html          Mission/story page
pricing.html        Honest "free today, model TBD" pricing page
docs.html           Build-from-source instructions + links to the real docs
src/main.ts         Homepage-only widgets: waveform, command demo, bento, phase track
src/common.ts       Shared entry point for about/pricing/docs (styles + scroll reveal only)
src/data.ts         Typed content: demo phrases, tool cards, roadmap phases
src/waveform.ts     Canvas waveform animation (Waveform class)
src/demo.ts         Multilingual command-demo cycler (CommandDemo class)
src/bento.ts        Renders the "what it controls" tool grid from data.ts
src/roadmap.ts      Renders the phase-track bar from data.ts
src/reveal.ts       Fade-in-on-scroll, shared by every page
src/style.css       All styling - CSS custom properties for light/dark theming
public/             Static assets copied as-is (favicon, etc.)
```

The header, topbar, and footer markup is duplicated across the four HTML
files rather than templated - there's no build-time include mechanism here.
Keep all four in sync by hand when nav or footer links change.

## Updating content

Change copy directly in the relevant `.html` file. Change the tool list,
roadmap phases, or demo phrases in `src/data.ts` - the homepage's DOM is
rendered from those arrays, so nothing else needs editing to add or reorder
an entry. Speculative product ideas beyond the committed roadmap belong in
`../future-scope.md`, not on the pricing or docs pages - keep those two
scoped to what's actually true today.

## Deploying

`npm run build` produces a fully static `dist/` - point Vercel/Netlify/GitHub
Pages at this directory (build command `npm run build`, publish directory
`dist`) with no server-side requirements.
